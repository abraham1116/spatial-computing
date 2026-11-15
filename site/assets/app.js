document.querySelectorAll("[data-copy]").forEach(function (btn) {
  btn.addEventListener("click", function () {
    var src = document.getElementById(btn.getAttribute("data-copy"));
    var text = src.innerText.replace(/\n{2,}/g, "\n").trim();
    var done = function (ok) {
      btn.textContent = ok ? "Copié" : "Sélectionne";
      setTimeout(function () { btn.textContent = "Copier"; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
    } else { done(false); }
  });
});
