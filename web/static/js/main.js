(() => {
  const form = document.getElementById("form-clasificar");
  if (!form) return;

  const textarea = document.getElementById("texto");
  const resultado = document.getElementById("resultado");
  const boton = document.getElementById("btn-enviar");

  document.querySelectorAll("[data-example]").forEach((chip) => {
    chip.addEventListener("click", () => {
      textarea.value = chip.getAttribute("data-example") || "";
      textarea.focus();
    });
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const texto = textarea.value.trim();
    resultado.hidden = false;
    resultado.className = "result";
    resultado.textContent = "Clasificando…";
    boton.disabled = true;

    try {
      const respuesta = await fetch("/api/clasificar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto }),
      });
      const data = await respuesta.json();
      if (!respuesta.ok) {
        throw new Error(data.error || "No se pudo clasificar.");
      }
      resultado.innerHTML = `
        <h2>${escapeHtml(data.modelo)}</h2>
        <p class="meta">Confianza ${Number(data.confianza).toFixed(2)} · ${escapeHtml(data.metodo)}</p>
        <div class="scores">
          ${Object.entries(data.puntajes)
            .map(
              ([nombre, valor]) =>
                `<div class="score"><span>${escapeHtml(nombre)}</span><strong>${Number(valor).toFixed(2)}</strong></div>`
            )
            .join("")}
        </div>
      `;
    } catch (error) {
      resultado.className = "result error";
      resultado.textContent = error.message;
    } finally {
      boton.disabled = false;
    }
  });

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
