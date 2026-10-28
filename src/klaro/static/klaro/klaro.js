// Progressive enhancement: native form submission and controls work without this file.

const FAILURE_MESSAGES = {
  0: "Klaro could not be reached. Check your connection and send the answers again. Your entries are still here.",
  404: "This questionnaire is no longer available. It may have expired or been closed.",
  409: "This questionnaire was already answered, possibly on another device. Reload the page to see the stored answers.",
};
const GENERIC_FAILURE =
  "The answers could not be sent. Please try again in a moment. Your entries are still here.";

const updateCounter = (input) => {
  const counter = document.getElementById(input.dataset.klCounter);
  if (!counter) {
    return;
  }
  const maximum = Number(input.dataset.klMax);
  const count = Array.from(input.value).length; // Code points, matching the server limit.
  counter.textContent = `${count} / ${maximum}`;
  counter.classList.toggle("kl-counter--over", count > maximum);
};

// Same rule as the server-rendered progress in _questionnaire_fragment.html: a question
// counts once an offered option is selected, or Other is selected with non-blank text.
const isAnswered = (fieldset) => {
  const checked = Array.from(fieldset.querySelectorAll("input:checked"));
  const other = fieldset.querySelector('textarea[name$="-other"]');
  return checked.some(
    (input) => input.value !== "other" || (other !== null && other.value.trim().length > 0),
  );
};

const update = () => {
  document.querySelectorAll("[data-kl-codepoint-input]").forEach(updateCounter);
  const form = document.querySelector("[data-kl-form]");
  const bar = document.querySelector("[data-kl-progress]");
  const label = document.querySelector("[data-kl-progress-count]");
  if (!form || !bar || !label) {
    return;
  }
  const fieldsets = Array.from(form.querySelectorAll("fieldset"));
  const answered = fieldsets.filter(isAnswered).length;
  bar.value = answered;
  label.textContent = `${answered} of ${fieldsets.length} answered`;
};

// A swap removes the focused submit button, so move focus to the new result.
// Alerts announce themselves; other results use the stable live region.
const focusSwapResult = () => {
  const target = document.querySelector("[data-kl-swap-focus]");
  const announcer = document.querySelector("[data-kl-announcer]");
  if (!target) {
    return;
  }
  target.focus();
  if (announcer && target.getAttribute("role") !== "alert") {
    announcer.textContent = target.textContent.trim();
  }
};

const showAlert = (selector, message) => {
  document.querySelectorAll("[data-kl-request-error], [data-kl-request-failed]").forEach((alert) => {
    alert.hidden = true;
  });
  const alert = document.querySelector(selector);
  if (!alert) {
    return;
  }
  if (message !== undefined) {
    alert.querySelector("[data-kl-request-failed-message]").textContent = message;
  }
  alert.hidden = false;
  alert.focus();
};

document.addEventListener("input", (event) => {
  if (event.target.matches("[data-kl-codepoint-input]")) {
    updateCounter(event.target);
  }
  if (event.target.closest("[data-kl-form]")) {
    update();
  }
});
document.addEventListener("change", (event) => {
  if (event.target.closest("[data-kl-form]")) {
    update();
  }
});
document.addEventListener("htmx:afterSwap", () => {
  update();
  focusSwapResult();
});
document.addEventListener("htmx:responseError", (event) => {
  const { status } = event.detail.xhr;
  if (status === 413) {
    showAlert("[data-kl-request-error]");
  } else {
    showAlert("[data-kl-request-failed]", FAILURE_MESSAGES[status] ?? GENERIC_FAILURE);
  }
});
document.addEventListener("htmx:sendError", () => {
  showAlert("[data-kl-request-failed]", FAILURE_MESSAGES[0]);
});

// Module scripts run after parsing, so the document is ready here.
update();
