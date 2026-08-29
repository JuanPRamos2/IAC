(() => {
  const form = document.getElementById("form-clasificar");
  if (!form) return;

  const resultado = document.getElementById("resultado");

  document.querySelectorAll("[data-example]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("texto").value = btn.getAttribute("data-example") || "";
    });
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const nombre = document.getElementById("nombre").value;
    const apellido = document.getElementById("apellido").value;
    const texto = document.getElementById("texto").value;
    const error = IacClassifier.validate(nombre, apellido, texto);
    resultado.hidden = false;
    if (error) {
      resultado.innerHTML = `<p class="error">${error}</p>`;
      return;
    }
    const out = IacClassifier.classify(texto);
    resultado.innerHTML = `
      <p class="note">${nombre.trim()} ${apellido.trim()}</p>
      <h2>Regex: ${out.regex.modelo}</h2>
      ${scoreGrid(out.regex.puntajes)}
      <h2>NLP: ${out.nlp.modelo}</h2>
      ${scoreGrid(out.nlp.puntajes)}
      <p class="note">Texto procesado: ${out.textoProcesado}</p>
    `;
  });

  function scoreGrid(puntajes) {
    return `<div class="scores">${IacClassifier.MODELS.map(
      (m) => `<div class="score"><span>${m}</span><strong>${puntajes[m]}</strong></div>`
    ).join("")}</div>`;
  }
})();
