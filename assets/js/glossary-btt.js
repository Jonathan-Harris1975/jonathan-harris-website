(function(){
  var btn = document.getElementById('bttBtn');
  if(!btn) return;
  window.addEventListener('scroll', function(){
    btn.classList.toggle('visible', window.scrollY > 400);
  }, {passive:true});
})();
