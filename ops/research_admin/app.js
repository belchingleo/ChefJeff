'use strict';
const base = '/research-admin/';
const el = id => document.getElementById(id);
const text = (tag, value, className) => {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
};
async function request(path) {
  const response = await fetch(base + path, {credentials:'same-origin', cache:'no-store'});
  if (response.status === 401) { location.assign(base+'login'); throw new Error('请重新登录。'); }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || '数据暂时不可用，请重试。');
  }
  return response.json();
}
function date(value, epoch=false) {
  if (!value) return '未记录';
  const d = new Date(epoch ? value*1000 : value);
  return Number.isNaN(d.valueOf()) ? '未记录' : d.toISOString().slice(0,19).replace('T',' ');
}
const login = el('login-form');
if (login) login.addEventListener('submit', async event => {
  event.preventDefault();
  const button = login.querySelector('button');
  button.disabled = true; el('login-error').textContent = '';
  try {
    const response = await fetch(login.action, {method:'POST', body:new URLSearchParams(new FormData(login)),credentials:'same-origin'});
    if (!response.ok) { const data = await response.json(); throw new Error(data.error || '登录失败。'); }
    location.assign(base);
  } catch (error) { el('login-error').textContent = error.message; button.disabled = false; }
});
