const state = { token: localStorage.getItem("nexum_token"), me: null };

const $ = (id) => document.getElementById(id);
const msg = (text, isError) => {
  const el = $("msg");
  el.hidden = !text;
  el.textContent = text || "";
  el.className = "msg" + (isError ? " error" : "");
};

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(`/api${path}`, { ...opts, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.mensaje || data.error || "Error");
  return data;
}

function mostrarLogin() {
  $("vista-login").hidden = false;
  $("vista-app").hidden = true;
  $("btn-salir").hidden = true;
  $("who").textContent = "";
}

function tabsPorPerfil(perfil) {
  const all = {
    COLAB: ["Encuesta"],
    LIDER_TURNO: ["Agregados"],
    AUDITOR: ["Agregados", "Bitácora"],
    ADMIN_SISTEMA: ["Catálogos", "Agregados", "Bitácora", "Umbral k"],
  };
  return all[perfil] || [];
}

async function entrar(me) {
  state.me = me;
  $("vista-login").hidden = true;
  $("vista-app").hidden = false;
  $("btn-salir").hidden = false;
  $("who").textContent = `${me.usuario_id} · ${me.perfil}`;
  const tabs = $("tabs");
  tabs.innerHTML = "";
  for (const nombre of tabsPorPerfil(me.perfil)) {
    const b = document.createElement("button");
    b.textContent = nombre;
    b.onclick = () => renderPanel(nombre);
    tabs.appendChild(b);
  }
  renderPanel(tabsPorPerfil(me.perfil)[0]);
}

async function renderPanel(nombre) {
  const panel = $("panel");
  if (nombre === "Encuesta") {
    const camps = await api("/catalogos/campanias");
    panel.innerHTML = `<h2>Autoreporte</h2>
      <form id="f-enc">
        <label>Campaña
          <select name="campania_id">${camps.data.map((c) => `<option value="${c.campania_id}">${c.nombre}</option>`).join("")}</select>
        </label>
        <div id="reactivos"></div>
        <button>Enviar</button>
      </form>`;
    const sel = panel.querySelector("select");
    const pintar = async () => {
      const c = camps.data.find((x) => x.campania_id === sel.value);
      const r = await api(`/catalogos/instrumentos/${c.instrumento_id}/versiones/${c.version_instrumento}/reactivos`);
      $("reactivos").innerHTML = r.data
        .map(
          (item) => `<div class="reactivo"><p>${item.orden}. ${item.texto}</p>
          <input type="range" min="${item.escala_min}" max="${item.escala_max}" value="3" data-id="${item.reactivo_id}">
          </div>`
        )
        .join("");
    };
    sel.onchange = pintar;
    await pintar();
    panel.querySelector("#f-enc").onsubmit = async (ev) => {
      ev.preventDefault();
      try {
        const respuestas = [...panel.querySelectorAll("input[data-id]")].map((i) => ({
          reactivo_id: i.dataset.id,
          valor: Number(i.value),
        }));
        const out = await api("/encuestas/respuestas", {
          method: "POST",
          body: JSON.stringify({
            seudonimo_id: state.me.seudonimo_id,
            campania_id: sel.value,
            respuestas,
          }),
        });
        msg(`Guardado ${out.id}`);
      } catch (e) {
        msg(e.message, true);
      }
    };
    return;
  }

  if (nombre === "Catálogos") {
    const [u, c] = await Promise.all([api("/catalogos/unidades"), api("/catalogos/campanias")]);
    panel.innerHTML = `<h2>Unidades</h2><ul>${u.data.map((x) => `<li>${x.unidad_organizacional_id} — ${x.nombre}</li>`).join("")}</ul>
      <h2>Campañas</h2><ul>${c.data.map((x) => `<li>${x.campania_id} — ${x.nombre}</li>`).join("")}</ul>`;
    return;
  }

  if (nombre === "Agregados") {
    const [u, c] = await Promise.all([api("/catalogos/unidades"), api("/catalogos/campanias")]);
    panel.innerHTML = `<h2>Agregado (umbral k)</h2>
      <label>Unidad <select id="u">${u.data.map((x) => `<option value="${x.unidad_organizacional_id}">${x.nombre}</option>`).join("")}</select></label>
      <label>Campaña <select id="c">${c.data.map((x) => `<option value="${x.campania_id}">${x.nombre}</option>`).join("")}</select></label>
      <button id="ver">Consultar</button>
      <pre id="out"></pre>`;
    panel.querySelector("#ver").onclick = async () => {
      try {
        const data = await api(`/agregados/${$("u").value}/${$("c").value}`);
        $("out").textContent = JSON.stringify(data, null, 2);
        msg(data.visible ? "Visible" : "Grupo insuficiente — no se exponen métricas");
      } catch (e) {
        msg(e.message, true);
      }
    };
    return;
  }

  if (nombre === "Bitácora") {
    const data = await api("/auditoria");
    panel.innerHTML = `<h2>Bitácora MongoDB</h2>
      <table><thead><tr><th>Acción</th><th>Actor</th><th>Perfil</th><th>Resultado</th><th>Cuando</th></tr></thead>
      <tbody>${data.data
        .map(
          (r) =>
            `<tr><td>${r.accion}</td><td>${r.actor_id}</td><td>${r.actor_perfil}</td><td>${r.resultado}</td><td>${r.timestamp}</td></tr>`
        )
        .join("")}</tbody></table>`;
    return;
  }

  if (nombre === "Umbral k") {
    panel.innerHTML = `<h2>Cambiar k</h2>
      <form id="fk"><label>Nuevo k <input name="k" type="number" min="2" max="50" value="5"></label>
      <button>Guardar</button></form>`;
    panel.querySelector("#fk").onsubmit = async (ev) => {
      ev.preventDefault();
      try {
        const k = Number(new FormData(ev.target).get("k"));
        await api("/agregados/parametros/k", { method: "PATCH", body: JSON.stringify({ k }) });
        msg(`k = ${k}`);
      } catch (e) {
        msg(e.message, true);
      }
    };
  }
}

$("form-login").onsubmit = async (ev) => {
  ev.preventDefault();
  msg("");
  const fd = new FormData(ev.target);
  try {
    const out = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ correo: fd.get("correo"), contrasena: fd.get("contrasena") }),
    });
    state.token = out.token;
    localStorage.setItem("nexum_token", out.token);
    await entrar(out);
  } catch (e) {
    msg(e.message, true);
  }
};

$("btn-salir").onclick = async () => {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch (_) {}
  state.token = null;
  localStorage.removeItem("nexum_token");
  mostrarLogin();
};

if (state.token) {
  api("/auth/me")
    .then(entrar)
    .catch(() => {
      state.token = null;
      localStorage.removeItem("nexum_token");
      mostrarLogin();
    });
}
