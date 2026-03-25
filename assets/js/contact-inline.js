window.jotformEmbedHandler("iframe[id='JotFormIFrame-260281179574362']", "https://form.jotform.com/");
    function isCompletedMessage(data) {
      if (!data) return false;
      if (typeof data === 'object') return data.action === 'submission-completed';
      if (typeof data !== 'string') return false;
      if (data.indexOf('submission-completed') === -1) return false;
      try {
        var parsed = JSON.parse(data);
        return parsed && parsed.action === 'submission-completed';
      } catch(err) {
        return data.indexOf('JotForm') > -1;
      }
    }
    window.addEventListener('message', function(e) {
      if (!isCompletedMessage(e.data)) return;
      var confirmation = document.getElementById('contact-form-confirmation');
      var formWrap = document.getElementById('contact-form-wrap');
      if (confirmation) {
        confirmation.hidden = false;
        confirmation.removeAttribute('hidden');
        confirmation.focus();
      }
      if (formWrap) {
        formWrap.setAttribute('hidden', '');
      }
    });
