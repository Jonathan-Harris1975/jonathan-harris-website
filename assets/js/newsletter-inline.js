(function(){
  function isCompletedMessage(data){
    if (!data) return false;
    if (typeof data === 'object') return data.action === 'submission-completed';
    if (typeof data !== 'string') return false;
    if (data.indexOf('submission-completed') === -1) return false;
    try {
      var parsed = JSON.parse(data);
      return parsed && parsed.action === 'submission-completed';
    } catch(_) {
      return data.indexOf('JotForm') > -1;
    }
  }
  window.addEventListener('message',function(e){
    if(!isCompletedMessage(e.data)) return;
    var w=document.getElementById('newsletter-form-wrap'),s=document.getElementById('newsletter-success');
    if(w&&s){w.setAttribute('hidden','');s.removeAttribute('hidden');s.focus();}
  });
})();
