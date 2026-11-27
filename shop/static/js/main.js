document.querySelectorAll('.flash').forEach(f=>setTimeout(()=>f.remove(),5000));
document.querySelectorAll('form[data-confirm]').forEach(f=>f.addEventListener('submit',e=>{if(!confirm(f.dataset.confirm))e.preventDefault()}));
const img=document.getElementById('imgInput');
if(img)img.addEventListener('change',()=>{const p=document.getElementById('preview');if(img.files[0]){p.src=URL.createObjectURL(img.files[0]);p.style.display='block'}});
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',()=>{navigator.clipboard.writeText(b.dataset.copy);b.textContent='Copied'}));
// stagger the entrance of cards/rows
document.querySelectorAll('.grid .card, table tr, .box').forEach((el,i)=>el.style.setProperty('--i',Math.min(i,12)));
// bump the cart counter after adding an item
if(sessionStorage.getItem('added')){const c=document.querySelector('nav a[href$="/cart"]');c&&c.classList.add('bump');sessionStorage.removeItem('added')}
document.querySelectorAll('form[action*="/cart/add/"]').forEach(f=>f.addEventListener('submit',()=>sessionStorage.setItem('added','1')));
