// Keeps the "n of m answered" progress in sync with the form; the page works without it.
(function () {
  function update() {
    var form = document.querySelector("[data-kl-form]");
    var bar = document.querySelector("[data-kl-progress]");
    var label = document.querySelector("[data-kl-progress-count]");
    if (!form || !bar || !label) {
      return;
    }
    var fieldsets = form.querySelectorAll("fieldset");
    var answered = 0;
    fieldsets.forEach(function (fieldset) {
      if (fieldset.querySelector("input:checked")) {
        answered += 1;
      }
    });
    bar.value = answered;
    label.textContent = answered + " of " + fieldsets.length + " answered";
  }

  document.addEventListener("change", function (event) {
    if (event.target.closest("[data-kl-form]")) {
      update();
    }
  });
  document.addEventListener("htmx:afterSwap", update);
  document.addEventListener("DOMContentLoaded", update);
})();
