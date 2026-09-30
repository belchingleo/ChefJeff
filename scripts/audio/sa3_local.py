"""Load Stable Audio 3 Small SFX from a local folder on CPU (Intel macOS friendly).

Intel Macs top out at torch 2.2.2, while stable-audio-3 pins torch 2.7.1. Two small shims make the
pinned library run on 2.2.2 + transformers 4.5x without touching its source:
  * T5Gemma's bidirectional attention masks are built by helpers that need torch>=2.6, so we pass
    the same additive 4D masks in directly;
  * torch.nn.functional.rms_norm (added in torch 2.4) gets an equivalent fallback.
"""
import json, os
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import numpy as np, soundfile as sf, torch
from stable_audio_3.loading_utils import load_diffusion_cond
from stable_audio_3.model import StableAudioModel

MODEL_DIR = os.environ.get("SA3_MODEL_DIR", "/Volumes/T7/AI-Models/stable-audio-3-small-sfx")
SAMPLE_RATE = 44100


def _patch_t5gemma_masks():
    from transformers.models.t5gemma import modeling_t5gemma as mt
    orig = mt.T5GemmaEncoder.forward

    def forward(self, input_ids=None, attention_mask=None, position_ids=None, inputs_embeds=None, **kw):
        if isinstance(attention_mask, torch.Tensor) and attention_mask.dim() == 2:
            ref = inputs_embeds if inputs_embeds is not None else self.embed_tokens.weight
            n = attention_mask.shape[1]
            keep = attention_mask.bool()[:, None, None, :].expand(-1, 1, n, n)
            idx = torch.arange(n, device=attention_mask.device)
            near = (idx[None, :] - idx[:, None]).abs() < self.config.sliding_window
            neg = torch.finfo(ref.dtype).min
            as_add = lambda m: torch.zeros(m.shape, dtype=ref.dtype, device=m.device).masked_fill(~m, neg)
            attention_mask = {"full_attention": as_add(keep), "sliding_attention": as_add(keep & near)}
        return orig(self, input_ids=input_ids, attention_mask=attention_mask,
                    position_ids=position_ids, inputs_embeds=inputs_embeds, **kw)

    mt.T5GemmaEncoder.forward = forward


_patch_t5gemma_masks()

if not hasattr(torch.nn.functional, "rms_norm"):
    def _rms_norm(x, normalized_shape, weight=None, eps=None):
        dims = tuple(range(-len(normalized_shape), 0))
        eps = torch.finfo(x.dtype).eps if eps is None else eps
        y = x * torch.rsqrt(x.pow(2).mean(dims, keepdim=True) + eps)
        return y * weight if weight is not None else y
    torch.nn.functional.rms_norm = _rms_norm


def load(device="cpu"):
    with open(f"{MODEL_DIR}/model_config.json") as f:
        cfg = json.load(f)
    for c in cfg["model"]["conditioning"]["configs"]:
        if c["type"] == "t5gemma":
            c["config"].pop("repo_id", None)
            c["config"].pop("subfolder", None)
            c["config"]["model_path"] = f"{MODEL_DIR}/t5gemma-b-b-ul2"
    model = load_diffusion_cond(cfg, f"{MODEL_DIR}/model.safetensors", device=device, model_half=False)
    model.use_lora, model.lora_names = False, []
    return StableAudioModel(model, cfg, device, False)


def generate(model, prompt, seconds, seed):
    """Return float32 audio shaped (samples, 2), peak-normalised."""
    a = model.generate(prompt=prompt, duration=seconds, seed=seed)[0].float().cpu().numpy().T
    return a / (np.abs(a).max() + 1e-8)


def save(path, audio):
    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
