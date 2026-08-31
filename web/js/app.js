const TOKEN_KEY = "nexum_token";
const state = { token: sessionStorage.getItem(TOKEN_KEY), me: null, seccion: null };

const MENSAJES = {
  CREDENCIALES_INVALIDAS: "Usuario o contraseña incorrectos.",
  CUENTA_BLOQUEADA: "La cuenta está temporalmente bloqueada. Intente de nuevo más tarde.",
  SIN_TOKEN: "Su sesión ha caducado. Inicie sesión nuevamente.",
  TOKEN_INVALIDO: "Su sesión ha caducado. Inicie sesión nuevamente.",
  TOKEN_REVOCADO: "La sesión se cerró. Inicie sesión nuevamente.",
  YA_RESPONDIO: "Ya envió esta evaluación. Solo se permite una respuesta por periodo.",
  SIN_CONSENTIMIENTO: "No es posible continuar hasta aceptar el aviso de privacidad vigente.",
  RBAC: "No tiene permiso para consultar esta sección.",
  CAMPANIA_INVALIDA: "La evaluación no está disponible en este momento.",
  CAMPANIA_NO_ASIGNADA: "Esta evaluación no corresponde a su equipo.",
  SEUDONIMO_INVALIDO: "No se encontró el participante indicado.",
  SEUDONIMO_AJENO: "No puede responder en nombre de otra persona.",
  PAYLOAD_INVALIDO: "Revise los datos e intente de nuevo.",
  K_INVALIDO: "Indique un número entre 2 y 50.",
  SIN_UNIDAD: "Su cuenta no tiene un equipo asignado.",
  SIN_SEUDONIMO: "Su cuenta no está habilitada para esta evaluación.",
  VALOR_FUERA_DE_ESCALA: "Alguna respuesta quedó fuera del rango permitido.",
  REACTIVO_FALTANTE: "Complete todas las preguntas obligatorias.",
};

const PERFIL_ETIQUETA = {
  COLAB: "Colaborador",
  LIDER_TURNO: "Líder de turno",
  AUDITOR: "Auditor de cumplimiento",
  ADMIN_SISTEMA: "Administrador",
};

const NAV = {
  COLAB: [{ id: "evaluacion", label: "Mi evaluación" }],
  LIDER_TURNO: [{ id: "resultados", label: "Resultados del equipo" }],
  AUDITOR: [
    { id: "resultados", label: "Resultados del equipo" },
    { id: "actividad", label: "Registro de actividad" },
    { id: "consentimiento", label: "Consentimientos" },
  ],
  ADMIN_SISTEMA: [
    { id: "organizacion", label: "Organización" },
    { id: "resultados", label: "Resultados del equipo" },
    { id: "actividad", label: "Registro de actividad" },
    { id: "consentimiento", label: "Consentimientos" },
    { id: "privacidad", label: "Privacidad" },
  ],
};

const ACCION_ETIQUETA = {
  LOGIN_EXITOSO: "Inicio de sesión",
  LOGIN_FALLIDO: "Acceso rechazado",
  LOGOUT: "Cierre de sesión",
  CREACION_RESPUESTA: "Envío de evaluación",
  CONSULTA_AGREGADO: "Consulta de resultados",
  CONSULTA_HISTORIAL_CONSENTIMIENTO: "Consulta de consentimiento",
  CAMBIO_UMBRAL_K: "Ajuste de privacidad",
};

const RECURSO_ETIQUETA = {
  USUARIO: "Cuenta",
  SEUDONIMO: "Participante",
  UNIDAD_ORGANIZACIONAL: "Equipo",
  PARAMETRO_GLOBAL: "Configuración",
  VERSION_CONSENTIMIENTO: "Aviso de privacidad",
  RESPUESTA_ENCUESTA: "Evaluación",
};

const RESULTADO_ETIQUETA = {
  EXITO: "Completado",
  RECHAZADO: "No autorizado",
  GRUPO_INSUFICIENTE: "Confidencialidad",
  ERROR_TECNICO: "No disponible",
};

const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function mensajeAmigable(data) {
  if (data?.error && MENSAJES[data.error]) return MENSAJES[data.error];
  return "No fue posible completar la operación. Intente de nuevo.";
}

function aviso(texto, esError = false) {
  const el = $("msg");
  if (!el) return;
  el.hidden = !texto;
  el.textContent = texto || "";
  el.className = "toast" + (esError ? " error" : "");
}

function errorLogin(texto) {
  const el = $("login-error");
  el.hidden = !texto;
  el.textContent = texto || "";
}

function formatFecha(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" });
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let res;
  try {
    res = await fetch(`/api${path}`, { ...opts, headers });
  } catch {
    throw new Error("No hay conexión con la plataforma. Intente más tarde.");
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && path !== "/auth/login") {
    state.token = null;
    sessionStorage.removeItem(TOKEN_KEY);
    mostrarLogin();
    throw new Error(MENSAJES.TOKEN_INVALIDO);
  }
  if (!res.ok) throw new Error(mensajeAmigable(data));
  return data;
}

function mostrarLogin() {
  document.body.classList.remove("is-auth");
  $("vista-login").hidden = false;
  $("vista-app").hidden = true;
  $("btn-salir").hidden = true;
  $("who").hidden = true;
  $("who").innerHTML = "";
  aviso("");
}

function opciones(lista, valueKey, labelKey) {
  return lista.map((x) => `<option value="${esc(x[valueKey])}">${esc(x[labelKey])}</option>`).join("");
}

async function entrar(me) {
  state.me = me;
  document.body.classList.add("is-auth");
  $("vista-login").hidden = true;
  $("vista-app").hidden = false;
  $("btn-salir").hidden = false;
  $("who").hidden = false;
  $("who").innerHTML = `<strong>${esc(PERFIL_ETIQUETA[me.perfil] || "Usuario")}</strong><span>Sesión activa</span>`;
  const tabs = $("tabs");
  tabs.innerHTML = "";
  const items = NAV[me.perfil] || [];
  for (const item of items) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = item.label;
    b.dataset.id = item.id;
    b.onclick = () => renderPanel(item.id);
    tabs.appendChild(b);
  }
  renderPanel(items[0]?.id);
}

function marcarNav(id) {
  state.seccion = id;
  for (const b of $("tabs").querySelectorAll("button")) {
    if (b.dataset.id === id) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  }
}

async function renderPanel(id) {
  marcarNav(id);
  const panel = $("panel");
  aviso("");
  panel.innerHTML = `<p class="empty">Cargando…</p>`;
  try {
    if (id === "evaluacion") return await panelEvaluacion(panel);
    if (id === "organizacion") return await panelOrganizacion(panel);
    if (id === "resultados") return await panelResultados(panel);
    if (id === "actividad") return await panelActividad(panel);
    if (id === "consentimiento") return await panelConsentimiento(panel);
    if (id === "privacidad") return await panelPrivacidad(panel);
  } catch (e) {
    panel.innerHTML = `<p class="empty">${esc(e.message)}</p>`;
    aviso(e.message, true);
  }
}

async function panelEvaluacion(panel) {
  const camps = await api("/catalogos/campanias");
  if (!camps.data.length) {
    panel.innerHTML = `<h2>Mi evaluación</h2>
      <p class="empty">Por ahora no hay evaluaciones abiertas para su equipo.</p>`;
    return;
  }
  panel.innerHTML = `<h2>Mi evaluación</h2>
    <p class="intro">Responda con sinceridad. Sus respuestas son estrictamente confidenciales y se procesan de forma anónima para proteger su identidad.</p>
    <div class="note">La información se usa solo para entender el bienestar del equipo, nunca para identificar a una persona.</div>
    <form id="f-enc">
      <label for="campania">Evaluación</label>
      <select id="campania" name="campania_id">${opciones(camps.data, "campania_id", "nombre")}</select>
      <p id="estado-campania" class="intro"></p>
      <div id="reactivos"></div>
      <div class="actions">
        <button class="btn btn-primary" type="submit" id="btn-enviar">Enviar respuestas</button>
      </div>
    </form>`;
  const sel = $("campania");
  const pintar = async () => {
    const c = camps.data.find((x) => x.campania_id === sel.value);
    const r = await api(`/catalogos/instrumentos/${c.instrumento_id}/versiones/${c.version_instrumento}/reactivos`);
    $("reactivos").innerHTML = r.data
      .map(
        (item) => `<div class="reactivo">
          <p>${esc(item.orden)}. ${esc(item.texto)}</p>
          <div class="escala">
            <small>En desacuerdo</small>
            <input type="range" min="${item.escala_min}" max="${item.escala_max}" value="3" data-id="${esc(item.reactivo_id)}" aria-label="Valoración">
            <small>De acuerdo</small>
          </div>
          <p class="escala-valor">Su valoración: <strong>3</strong> de ${esc(item.escala_max)}</p>
        </div>`
      )
      .join("");
    panel.querySelectorAll("input[type=range]").forEach((input) => {
      const etiqueta = input.closest(".reactivo").querySelector(".escala-valor strong");
      input.addEventListener("input", () => {
        etiqueta.textContent = input.value;
      });
    });
    const est = await api(`/encuestas/estado?campania_id=${encodeURIComponent(sel.value)}`);
    const avisoEstado = $("estado-campania");
    const btn = $("btn-enviar");
    if (est.ya_respondio) {
      avisoEstado.textContent = "Ya envió esta evaluación. Gracias por participar.";
      btn.disabled = true;
    } else {
      avisoEstado.textContent = "Aún no ha enviado esta evaluación.";
      btn.disabled = false;
    }
  };
  sel.onchange = pintar;
  await pintar();
  $("f-enc").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const respuestas = [...panel.querySelectorAll("input[data-id]")].map((i) => ({
        reactivo_id: i.dataset.id,
        valor: Number(i.value),
      }));
      await api("/encuestas/respuestas", {
        method: "POST",
        body: JSON.stringify({
          seudonimo_id: state.me.seudonimo_id,
          campania_id: sel.value,
          respuestas,
        }),
      });
      aviso("Sus respuestas se guardaron correctamente. Gracias por su participación.");
      await pintar();
    } catch (e) {
      aviso(e.message, true);
    }
  };
}

async function panelOrganizacion(panel) {
  const [u, c, i] = await Promise.all([
    api("/catalogos/unidades"),
    api("/catalogos/campanias"),
    api("/catalogos/instrumentos"),
  ]);
  const tipo = (t) => (t === "NOM035" ? "Factores de riesgo psicosocial" : t === "CLIMA" ? "Clima laboral" : t);
  panel.innerHTML = `<h2>Organización</h2>
    <p class="intro">Equipos, evaluaciones vigentes e instrumentos de medición disponibles en la plataforma.</p>
    <h3>Equipos</h3>
    <ul class="list-cards">${u.data.map((x) => `<li>${esc(x.nombre)}</li>`).join("")}</ul>
    <h3>Evaluaciones</h3>
    <ul class="list-cards">${c.data.map((x) => `<li>${esc(x.nombre)}<br><small>${esc(x.fecha_inicio)} — ${esc(x.fecha_fin)}</small></li>`).join("")}</ul>
    <h3>Instrumentos</h3>
    <ul class="list-cards">${i.data.map((x) => `<li>${esc(x.nombre)}<br><small>${esc(tipo(x.tipo))}</small></li>`).join("")}</ul>`;
}

async function panelResultados(panel) {
  const [u, c] = await Promise.all([api("/catalogos/unidades"), api("/catalogos/campanias")]);
  if (!u.data.length || !c.data.length) {
    panel.innerHTML = `<h2>Resultados del equipo</h2>
      <p class="empty">No hay equipos o evaluaciones visibles para su perfil.</p>`;
    return;
  }
  panel.innerHTML = `<h2>Resultados del equipo</h2>
    <p class="intro">Los resultados solo se muestran cuando hay suficientes respuestas. Así se protege la confidencialidad de cada persona.</p>
    <div class="filters">
      <div>
        <label for="u">Equipo</label>
        <select id="u">${opciones(u.data, "unidad_organizacional_id", "nombre")}</select>
      </div>
      <div>
        <label for="c">Evaluación</label>
        <select id="c">${opciones(c.data, "campania_id", "nombre")}</select>
      </div>
      <button type="button" class="btn btn-primary" id="ver">Ver resultados</button>
    </div>
    <div id="resultado"></div>`;
  $("ver").onclick = async () => {
    const caja = $("resultado");
    caja.innerHTML = `<p class="empty">Consultando…</p>`;
    try {
      const campaniaId = $("c").value;
      const campania = c.data.find((x) => x.campania_id === campaniaId);
      const [data, reactivos] = await Promise.all([
        api(`/agregados/${encodeURIComponent($("u").value)}/${encodeURIComponent(campaniaId)}`),
        api(`/catalogos/instrumentos/${campania.instrumento_id}/versiones/${campania.version_instrumento}/reactivos`),
      ]);
      if (!data.visible) {
        caja.innerHTML = `<div class="aviso">Aún no hay suficientes respuestas para mostrar resultados de este equipo. Esta medida evita que alguien pueda ser identificado.</div>`;
        return;
      }
      const nombres = Object.fromEntries(reactivos.data.map((r) => [r.reactivo_id, r.texto]));
      const detalle = Object.entries(data.detalle || {});
      caja.innerHTML = `<div class="metrics">
          <div class="metric"><span>Participación</span><strong>${esc(data.total_respuestas)}</strong></div>
          <div class="metric"><span>Promedio general</span><strong>${esc(data.promedio_global)}</strong></div>
          <div class="metric"><span>Mínimo para publicar</span><strong>${esc(data.k)}</strong></div>
        </div>
        ${detalle
          .map(([id, valor]) => {
            const ancho = Math.max(0, Math.min(100, (Number(valor) / 5) * 100));
            return `<div class="bar-row"><p>${esc(nombres[id] || "Indicador")} · ${esc(valor)}</p>
              <div class="bar" aria-hidden="true"><i style="width:${ancho}%"></i></div></div>`;
          })
          .join("")}`;
    } catch (e) {
      caja.innerHTML = "";
      aviso(e.message, true);
    }
  };
}

async function panelActividad(panel) {
  const data = await api("/auditoria");
  if (!data.data.length) {
    panel.innerHTML = `<h2>Registro de actividad</h2><p class="empty">Todavía no hay actividad registrada.</p>`;
    return;
  }
  panel.innerHTML = `<h2>Registro de actividad</h2>
    <p class="intro">Seguimiento de accesos, consultas y cambios de configuración, sin datos personales de las evaluaciones.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Actividad</th><th>Ámbito</th><th>Cuenta</th><th>Perfil</th><th>Resultado</th><th>Fecha</th></tr></thead>
      <tbody>${data.data
        .map(
          (r) => `<tr>
            <td>${esc(ACCION_ETIQUETA[r.accion] || "Actividad")}</td>
            <td>${esc(RECURSO_ETIQUETA[r.recurso] || "—")}</td>
            <td>${esc(r.actor_id === "DESCONOCIDO" ? "No identificado" : r.actor_id)}</td>
            <td>${esc(PERFIL_ETIQUETA[r.actor_perfil] || r.actor_perfil || "—")}</td>
            <td>${esc(RESULTADO_ETIQUETA[r.resultado] || r.resultado)}</td>
            <td>${esc(formatFecha(r.timestamp))}</td>
          </tr>`
        )
        .join("")}</tbody>
    </table></div>`;
}

async function panelConsentimiento(panel) {
  panel.innerHTML = `<h2>Consentimientos</h2>
    <p class="intro">Consulte el historial de aceptación del aviso de privacidad de un participante, sin exponer su identidad laboral.</p>
    <form id="f-cons">
      <label for="codigo">Código de participante</label>
      <input id="codigo" name="codigo" required placeholder="Ingrese el código asignado" autocomplete="off">
      <div class="actions">
        <button class="btn btn-primary" type="submit">Consultar</button>
      </div>
    </form>
    <div id="out-cons"></div>`;
  $("f-cons").onsubmit = async (ev) => {
    ev.preventDefault();
    const caja = $("out-cons");
    caja.innerHTML = `<p class="empty">Consultando…</p>`;
    try {
      const id = new FormData(ev.target).get("codigo").trim();
      const data = await api(`/auditoria/consentimientos/${encodeURIComponent(id)}`);
      if (!data.data.length) {
        caja.innerHTML = `<p class="empty">No hay registros de consentimiento para este código.</p>`;
        return;
      }
      caja.innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>Versión del aviso</th><th>Aceptado</th><th>Revocado</th><th>Estado</th></tr></thead>
        <tbody>${data.data
          .map(
            (f) => `<tr>
              <td>${esc(f.version_consentimiento_id)}</td>
              <td>${esc(formatFecha(f.fecha_aceptacion))}</td>
              <td>${esc(f.fecha_revocacion ? formatFecha(f.fecha_revocacion) : "Vigente")}</td>
              <td>${esc(f.estado === "ACEPTADO" ? "Aceptado" : f.estado)}</td>
            </tr>`
          )
          .join("")}</tbody></table></div>`;
    } catch (e) {
      caja.innerHTML = "";
      aviso(e.message, true);
    }
  };
}

async function panelPrivacidad(panel) {
  const actual = await api("/agregados/parametros/k");
  panel.innerHTML = `<h2>Privacidad de resultados</h2>
    <p class="intro">Defina cuántas respuestas debe haber en un equipo antes de publicar promedios. Un umbral más alto protege mejor a las personas.</p>
    <div class="note">Valor actual: se requieren al menos <strong>${esc(actual.k)}</strong> respuestas para mostrar resultados.</div>
    <form id="fk">
      <label for="k">Número mínimo de respuestas</label>
      <input id="k" name="k" type="number" min="2" max="50" value="${esc(actual.k)}" required>
      <div class="actions">
        <button class="btn btn-primary" type="submit">Guardar</button>
      </div>
    </form>`;
  $("fk").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const k = Number(new FormData(ev.target).get("k"));
      await api("/agregados/parametros/k", { method: "PATCH", body: JSON.stringify({ k }) });
      aviso("El umbral de privacidad se actualizó correctamente.");
      await panelPrivacidad(panel);
    } catch (e) {
      aviso(e.message, true);
    }
  };
}

$("form-login").onsubmit = async (ev) => {
  ev.preventDefault();
  errorLogin("");
  const fd = new FormData(ev.target);
  const correo = String(fd.get("correo") || "").trim();
  const contrasena = String(fd.get("contrasena") || "");
  if (!correo || !contrasena) {
    errorLogin("Ingrese su correo y contraseña.");
    return;
  }
  try {
    const out = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ correo, contrasena }),
    });
    state.token = out.token;
    sessionStorage.setItem(TOKEN_KEY, out.token);
    await entrar(out);
  } catch (e) {
    errorLogin(e.message);
  }
};

$("btn-salir").onclick = async () => {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch (_) {}
  state.token = null;
  sessionStorage.removeItem(TOKEN_KEY);
  $("form-login").reset();
  errorLogin("");
  mostrarLogin();
};

if (state.token) {
  api("/auth/me")
    .then(entrar)
    .catch(() => {
      state.token = null;
      sessionStorage.removeItem(TOKEN_KEY);
      mostrarLogin();
    });
}
