(() => {
  const root = document.body.getAttribute("data-root") || ".";
  const page = document.body.getAttribute("data-page") || "";
  const prefix = root.replace(/\/$/, "");

  const header = document.getElementById("site-header");
  if (header) {
    header.innerHTML = `
      <div class="site-nav wrap">
        <a class="brand" href="${prefix}/index.html">SC3705</a>
        <nav>
          <a href="${prefix}/index.html" data-nav="inicio">Inicio</a>
          <a href="${prefix}/ejercicios.html" data-nav="ejercicios">Ejercicios</a>
          <a href="${prefix}/simulador.html" data-nav="simulador">Simulador</a>
        </nav>
      </div>`;
    header.querySelectorAll("[data-nav]").forEach((link) => {
      if (link.getAttribute("data-nav") === page) {
        link.setAttribute("aria-current", "page");
      }
    });
  }

  const footer = document.getElementById("site-footer");
  if (footer) {
    footer.classList.add("site-footer");
    footer.innerHTML = `<div class="wrap">Juan Pablo Ramos Salazar · matrícula 610248 · Universidad de Monterrey · SC3705</div>`;
  }

  const list = document.getElementById("exercise-list");
  if (list) {
    const exercises = [
      {
        href: "ejercicios/eg01.html",
        title: "Ejercicio guiado 1",
        note: "Clasificador Cloud (Java GUI/CLI y simulador web).",
      },
    ];
    list.innerHTML = exercises
      .map(
        (ex) => `
        <article class="exercise-card">
          <h2>${ex.title}</h2>
          <p class="note">${ex.note}</p>
          <p><a href="${ex.href}">Abrir →</a></p>
        </article>`
      )
      .join("");
  }

  document.querySelectorAll("img.shot").forEach((img) => {
    img.addEventListener("error", () => {
      const box = document.createElement("div");
      box.className = "shot-missing";
      box.textContent = `Falta la captura ${img.getAttribute("src")}. Cópiala desde tu máquina a web/img/screenshots/.`;
      img.replaceWith(box);
    });
  });
})();
