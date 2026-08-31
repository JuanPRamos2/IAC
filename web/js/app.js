const TOKEN_KEY = "nexum_token";
const state = { token: sessionStorage.getItem(TOKEN_KEY), me: null };

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

async function pintarSalud() {
  const el = $("salud");
  if (!el) return;
  try {
    const s = await fetch("/api/salud").then((r) => r.json());
    el.textContent = s.ok
      ? "PostgreSQL · MongoDB · Redis conectados"
      : `Servicios: PG ${s.postgres ? "ok" : "no"} · Mongo ${s.mongo ? "ok" : "no"} · Redis ${s.redis ? "ok" : "no"}`;
    el.className = "salud" + (s.ok ? "" : " error");
  } catch {
    el.textContent = "API no disponible";
    el.className = "salud error";
  }
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
    AUDITOR: ["Agregados", "Bitácora", "Consentimiento"],
    ADMIN_SISTEMA: ["Catálogos", "Agregados", "Bitácora", "Consentimiento", "Umbral k"],
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
    b.type = "button";
    b.textContent = nombre;
    b.onclick = () => renderPanel(nombre);
    tabs.appendChild(b);
  }
  renderPanel(tabsPorPerfil(me.perfil)[0]);
}

function opciones(lista, valueKey, labelKey) {
  return lista.map((x) => `<option value="${x[valueKey]}">${x[labelKey]}</option>`).join("");
}

async function renderPanel(nombre) {
  const panel = $("panel");
  msg("");

  if (nombre === "Encuesta") {
    const camps = await api("/catalogos/campanias");
    if (!camps.data.length) {
      panel.innerHTML = "<h2>Autoreporte</h2><p>No hay campañas asignadas a tu unidad.</p>";
      return;
    }
    panel.innerHTML = `<h2>Autoreporte</h2>
      <p class="muted">Se valida en PostgreSQL (seudónimo, campaña, consentimiento) y se inserta en MongoDB <code>respuestas_encuesta</code> sin <code>empleado_id</code>.</p>
      <form id="f-enc">
        <label>Campaña
          <select name="campania_id">${opciones(camps.data, "campania_id", "nombre")}</select>
        </label>
        <p id="estado-campania" class="muted"></p>
        <div id="reactivos"></div>
        <button type="submit" id="btn-enviar">Enviar</button>
      </form>`;
    const sel = panel.querySelector("select");
    const pintar = async () => {
      const c = camps.data.find((x) => x.campania_id === sel.value);
      const r = await api(`/catalogos/instrumentos/${c.instrumento_id}/versiones/${c.version_instrumento}/reactivos`);
      $("reactivos").innerHTML = r.data
        .map(
          (item) => `<div class="reactivo"><p>${item.orden}. ${item.texto}</p>
          <input type="range" min="${item.escala_min}" max="${item.escala_max}" value="3" data-id="${item.reactivo_id}">
          <span class="valor">3</span>
          </div>`
        )
        .join("");
      panel.querySelectorAll("input[type=range]").forEach((input) => {
        input.addEventListener("input", () => {
          input.nextElementSibling.textContent = input.value;
        });
      });
      try {
        const est = await api(`/encuestas/estado?campania_id=${encodeURIComponent(sel.value)}`);
        const aviso = $("estado-campania");
        const btn = $("btn-enviar");
        if (est.ya_respondio) {
          aviso.textContent = "Ya enviaste esta campaña (RN-01). No se puede duplicar.";
          btn.disabled = true;
        } else {
          aviso.textContent = "Aún no hay respuesta registrada para esta campaña.";
          btn.disabled = false;
        }
      } catch (e) {
        msg(e.message, true);
      }
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
        msg(`Guardado ${out.id} · consentimiento ${out.version_consentimiento}`);
        await pintar();
      } catch (e) {
        msg(e.message, true);
      }
    };
    return;
  }

  if (nombre === "Catálogos") {
    const [u, c, i] = await Promise.all([
      api("/catalogos/unidades"),
      api("/catalogos/campanias"),
      api("/catalogos/instrumentos"),
    ]);
    panel.innerHTML = `<h2>Unidades (organizacion)</h2><ul>${u.data.map((x) => `<li>${x.unidad_organizacional_id} — ${x.nombre}</li>`).join("")}</ul>
      <h2>Campañas (catalogo)</h2><ul>${c.data.map((x) => `<li>${x.campania_id} — ${x.nombre}</li>`).join("")}</ul>
      <h2>Instrumentos (catalogo)</h2><ul>${i.data.map((x) => `<li>${x.instrumento_id} — ${x.nombre} (${x.tipo})</li>`).join("")}</ul>`;
    return;
  }

  if (nombre === "Agregados") {
    const [u, c] = await Promise.all([api("/catalogos/unidades"), api("/catalogos/campanias")]);
    if (!u.data.length || !c.data.length) {
      panel.innerHTML = "<h2>Agregado (umbral k)</h2><p>No hay unidades o campañas visibles para tu perfil.</p>";
      return;
    }
    panel.innerHTML = `<h2>Agregado (umbral k / RN-04)</h2>
      <p class="muted">Si n &lt; k el API responde <code>GRUPO_INSUFICIENTE</code> sin totales ni promedios.</p>
      <label>Unidad <select id="u">${opciones(u.data, "unidad_organizacional_id", "nombre")}</select></label>
      <label>Campaña <select id="c">${opciones(c.data, "campania_id", "nombre")}</select></label>
      <button type="button" id="ver">Consultar</button>
      <div id="aviso-k" class="aviso" hidden></div>
      <pre id="out"></pre>`;
    panel.querySelector("#ver").onclick = async () => {
      try {
        const data = await api(`/agregados/${encodeURIComponent($("u").value)}/${encodeURIComponent($("c").value)}`);
        $("out").textContent = JSON.stringify(data, null, 2);
        const aviso = $("aviso-k");
        if (data.visible) {
          aviso.hidden = true;
          msg(`Visible · ${data.total_respuestas} respuestas · k=${data.k}`);
        } else {
          aviso.hidden = false;
          aviso.textContent = `Grupo insuficiente (n < k=${data.k}). No se exponen totales ni promedios.`;
          msg("Grupo insuficiente — no se exponen métricas");
        }
      } catch (e) {
        msg(e.message, true);
      }
    };
    return;
  }

  if (nombre === "Bitácora") {
    const data = await api("/auditoria");
    panel.innerHTML = `<h2>Bitácora MongoDB</h2>
      <p class="muted">Códigos validados contra <code>auditoria.tipo_accion</code>, <code>tipo_recurso</code> y <code>resultado_auditoria</code>.</p>
      <table><thead><tr><th>Acción</th><th>Recurso</th><th>Actor</th><th>Perfil</th><th>Resultado</th><th>Cuando</th></tr></thead>
      <tbody>${data.data
        .map(
          (r) =>
            `<tr><td>${r.accion}</td><td>${r.recurso}</td><td>${r.actor_id}</td><td>${r.actor_perfil}</td><td>${r.resultado}</td><td>${r.timestamp}</td></tr>`
        )
        .join("")}</tbody></table>`;
    return;
  }

  if (nombre === "Consentimiento") {
    panel.innerHTML = `<h2>Historial de consentimiento</h2>
      <p class="muted">Solo IDs operativos. Nunca se devuelve <code>empleado_id</code>.</p>
      <form id="f-cons">
        <label>seudonimo_id <input name="seudonimo_id" required placeholder="SEUD-2026-014892" value="SEUD-2026-014892"></label>
        <button type="submit">Consultar</button>
      </form>
      <pre id="out-cons"></pre>`;
    panel.querySelector("#f-cons").onsubmit = async (ev) => {
      ev.preventDefault();
      try {
        const id = new FormData(ev.target).get("seudonimo_id");
        const data = await api(`/auditoria/consentimientos/${encodeURIComponent(id)}`);
        $("out-cons").textContent = JSON.stringify(data, null, 2);
        msg(`Historial de ${data.seudonimo_id}`);
      } catch (e) {
        msg(e.message, true);
      }
    };
    return;
  }

  if (nombre === "Umbral k") {
    const actual = await api("/agregados/parametros/k");
    panel.innerHTML = `<h2>Cambiar k</h2>
      <p class="muted">Valor actual: <strong>${actual.k}</strong>. El cambio invalida <code>cache:agregado:*</code> y se audita como CAMBIO_UMBRAL_K.</p>
      <form id="fk"><label>Nuevo k <input name="k" type="number" min="2" max="50" value="${actual.k}"></label>
      <button type="submit">Guardar</button></form>`;
    panel.querySelector("#fk").onsubmit = async (ev) => {
      ev.preventDefault();
      try {
        const k = Number(new FormData(ev.target).get("k"));
        await api("/agregados/parametros/k", { method: "PATCH", body: JSON.stringify({ k }) });
        msg(`k = ${k}. Caché Redis de agregados invalidada.`);
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
    sessionStorage.setItem(TOKEN_KEY, out.token);
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
  sessionStorage.removeItem(TOKEN_KEY);
  mostrarLogin();
};

pintarSalud();
setInterval(pintarSalud, 30000);

if (state.token) {
  api("/auth/me")
    .then(entrar)
    .catch(() => {
      state.token = null;
      sessionStorage.removeItem(TOKEN_KEY);
      mostrarLogin();
    });
}
