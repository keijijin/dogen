(function () {
  function gradeFieldset(fs) {
    var correct = fs.getAttribute("data-correct-index");
    if (correct === null || correct === "") return;
    var want = parseInt(correct, 10);
    if (isNaN(want)) return;
    var inputs = fs.querySelectorAll('input[type="radio"]');
    var sel = -1;
    for (var i = 0; i < inputs.length; i++) {
      if (inputs[i].checked) sel = i;
    }
    var msg = fs.querySelector(".quiz__result");
    if (!msg) {
      msg = document.createElement("p");
      msg.className = "quiz__result";
      msg.setAttribute("role", "status");
      fs.appendChild(msg);
    }
    if (sel < 0) {
      msg.textContent = "選択してください。";
      msg.style.color = "#6b5344";
      return;
    }
    if (sel === want) {
      msg.textContent = "正解です。";
      msg.style.color = "#2d5a3d";
    } else {
      msg.textContent = "不正解です。本文をあわせて読み直してみてください。";
      msg.style.color = "#8b2942";
    }
  }

  function initFieldset(fs) {
    var inputs = fs.querySelectorAll('input[type="radio"]');
    for (var i = 0; i < inputs.length; i++) inputs[i].disabled = false;
    if (fs.getAttribute("data-correct-index") === null) return;
    var btn = fs.querySelector(".quiz__btn");
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "quiz__btn btn btn--ghost";
      btn.textContent = "この設問を採点";
      btn.addEventListener("click", function () {
        gradeFieldset(fs);
      });
      fs.appendChild(btn);
    }
  }

  document.querySelectorAll("fieldset.quiz").forEach(function (fs) {
    initFieldset(fs);
  });
})();
