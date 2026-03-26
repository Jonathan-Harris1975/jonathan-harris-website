(function(){
  function encodeBody(value){
    return encodeURIComponent(value).replace(/%20/g, ' ');
  }

  function handleSubmit(event){
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches('[data-mailto-form]')) return;
    event.preventDefault();

    var recipient = form.getAttribute('data-mailto-recipient') || 'hello@jonathan-harris.online';
    var subjectPrefix = form.getAttribute('data-mailto-subject-prefix') || '';
    var statusId = form.getAttribute('data-mailto-status');
    var status = statusId ? document.getElementById(statusId) : null;
    var requiredFields = Array.prototype.slice.call(form.querySelectorAll('[required]'));
    for (var i = 0; i < requiredFields.length; i += 1) {
      if (!requiredFields[i].value.trim()) {
        requiredFields[i].focus();
        if (status) {
          status.textContent = 'Please complete the required fields before opening your email app.';
        }
        return;
      }
    }

    var lines = [];
    Array.prototype.slice.call(form.elements).forEach(function(field){
      if (!field.name || field.disabled) return;
      if ((field.type === 'submit') || (field.type === 'button')) return;
      var value = (field.value || '').trim();
      if (!value) return;
      var label = field.getAttribute('data-label') || field.name;
      lines.push(label + ': ' + value);
    });

    var subjectSource = form.querySelector('[name="subject"]');
    var subjectTail = subjectSource && subjectSource.value.trim() ? subjectSource.value.trim() : (form.getAttribute('data-mailto-subject') || 'Website enquiry');
    var subject = subjectPrefix ? (subjectPrefix + ': ' + subjectTail) : subjectTail;
    var body = lines.join('\n');
    var href = 'mailto:' + encodeURIComponent(recipient) + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeBody(body);

    if (status) {
      status.textContent = 'Opening your email app with everything filled in.';
    }
    window.location.href = href;
  }

  document.addEventListener('submit', handleSubmit);
})();
