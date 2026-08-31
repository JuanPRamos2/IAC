const TOKEN_KEY = "nexum_token";
const state = { token: sessionStorage.getItem(TOKEN_KEY), me: null, seccion: null, evalFase: "intro" };

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
  REACTIVO_DESCONOCIDO: "El cuestionario no coincide con la evaluación actual.",
  ERROR_TECNICO: "El servicio no está disponible por un momento. Intente de nuevo.",
  SIN_SESION: "Inicie sesión para continuar.",
};

const PERFIL_ETIQUETA = {
  COLAB: "Colaborador",
  LIDER_TURNO: "Líder de turno",
  AUDITOR: "Auditor de cumplimiento",
  ADMIN_SISTEMA: "Administrador",
};

const NAV = {
  COLAB: [
    { id: "inicio", label: "Inicio" },
    { id: "evaluacion", label: "Evaluación" },
    { id: "tendencias", label: "Mis tendencias" },
    { id: "privacidad-colab", label: "Privacidad" },
    { id: "apoyo", label: "Solicitar apoyo" },
  ],
  LIDER_TURNO: [
    { id: "resultados", label: "Resultados del equipo" },
    { id: "privacidad-lider", label: "Límites de privacidad" },
  ],
  AUDITOR: [
    { id: "resultados", label: "Métricas agregadas" },
    { id: "privacidad-auditor", label: "Cumplimiento" },
    { id: "actividad", label: "Bitácora" },
    { id: "consentimiento", label: "Consentimientos" },
    { id: "soporte", label: "Solicitudes de apoyo" },
  ],
  ADMIN_SISTEMA: [
    { id: "organizacion", label: "Instrumentos y equipos" },
    { id: "cuentas", label: "Cuentas y perfiles" },
    { id: "privacidad", label: "Parámetros globales" },
    { id: "resultados", label: "Métricas agregadas" },
    { id: "actividad", label: "Bitácora" },
  ],
};

const ACCION_ETIQUETA = {
  LOGIN_EXITOSO: "Inicio de sesión",
  LOGIN_FALLIDO: "Acceso rechazado",
  LOGOUT: "Cierre de sesión",
  CREACION_RESPUESTA: "Envío de evaluación",
  CONSULTA_AGREGADO: "Consulta de resultados",
  CONSULTA_HISTORIAL_CONSENTIMIENTO: "Consulta de consentimiento",
  CAMBIO_UMBRAL_K: "Ajuste de umbral de privacidad",
  CAMBIO_CONSENTIMIENTO: "Cambio de consentimiento",
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

function formatDia(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso || "—");
  return d.toLocaleDateString("es-MX", { dateStyle: "medium" });
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (opts.body) headers["Content-Type"] = "application/json";
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
  return (lista || []).map((x) => `<option value="${esc(x[valueKey])}">${esc(x[labelKey])}</option>`).join("");
}

async function entrar(me) {
  state.me = me;
  state.evalFase = "intro";
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
    const vistas = {
      inicio: panelInicio,
      evaluacion: panelEvaluacion,
      tendencias: panelTendencias,
      "privacidad-colab": panelPrivacidadColab,
      apoyo: panelApoyo,
      resultados: panelResultados,
      "privacidad-lider": panelPrivacidadLider,
      "privacidad-auditor": panelPrivacidadAuditor,
      organizacion: panelOrganizacion,
      cuentas: panelCuentas,
      actividad: panelActividad,
      consentimiento: panelConsentimiento,
      soporte: panelSoporte,
      privacidad: panelPrivacidad,
    };
    const fn = vistas[id];
    if (fn) await fn(panel);
  } catch (e) {
    panel.innerHTML = `<h2>No se pudo abrir esta sección</h2>
      <p class="intro">${esc(e.message)}</p>
      <div class="actions"><button type="button" class="btn btn-primary" id="reintentar">Reintentar</button></div>`;
    $("reintentar").onclick = () => renderPanel(id);
  }
}

function cards(items) {
  return `<div class="cards-grid">${items
    .map(
      (x) => `<button type="button" class="nav-card" data-go="${esc(x.id)}">
        <strong>${esc(x.title)}</strong>
        <span>${esc(x.text)}</span>
      </button>`
    )
    .join("")}</div>`;
}

function bindCards(panel) {
  panel.querySelectorAll("[data-go]").forEach((b) => {
    b.onclick = () => renderPanel(b.dataset.go);
  });
}

async function panelInicio(panel) {
  panel.innerHTML = `<h2>Bienvenido</h2>
    <p class="intro">Este espacio es confidencial. Sus respuestas no se muestran a su líder de forma individual.</p>
    ${cards([
      { id: "evaluacion", title: "Completar evaluación", text: "Autoreporte de carga de trabajo y clima laboral." },
      { id: "privacidad-colab", title: "Consentimiento y privacidad", text: "Aceptar, pausar o revocar su participación." },
      { id: "tendencias", title: "Mis tendencias", text: "Consulte el historial de las evaluaciones que usted envió." },
      { id: "apoyo", title: "Solicitar apoyo", text: "Pida orientación de bienestar sin exponer su identidad laboral." },
    ])}
    <div class="note">La vinculación de wearables y las recomendaciones automáticas avanzadas se habilitan en una fase posterior. En este producto mínimo puede evaluar, gestionar su consentimiento y pedir apoyo.</div>`;
  bindCards(panel);
}

async function panelEvaluacion(panel) {
  const desk = await api("/portal/escritorio");
  const lista = desk.campanias || [];
  if (!lista.length) {
    panel.innerHTML = `<h2>Evaluación</h2><p class="empty">Por ahora no hay evaluaciones abiertas para su equipo.</p>`;
    return;
  }

  const pintarFase = async () => {
    const campania = lista[0];
    let ya = false;
    try {
      const est = await api(`/encuestas/estado?campania_id=${encodeURIComponent(campania.campania_id)}`);
      ya = Boolean(est.ya_respondio);
    } catch (_) {}

    if (state.evalFase === "exito") {
      panel.innerHTML = `<div class="phase-screen phase-ok">
        <p class="eyebrow">Listo</p>
        <h2>Gracias por completar su evaluación</h2>
        <p class="intro">Sus respuestas se guardaron de forma anónima. Nadie de su equipo verá un resultado individual. Cuando haya suficientes participaciones, su líder solo verá promedios del grupo.</p>
        <div class="actions">
          <button type="button" class="btn btn-primary" data-go="tendencias">Ver mis tendencias</button>
          <button type="button" class="btn btn-secondary" data-go="inicio">Volver al inicio</button>
        </div>
      </div>`;
      bindCards(panel);
      return;
    }

    if (ya) {
      panel.innerHTML = `<div class="phase-screen">
        <p class="eyebrow">Participación</p>
        <h2>Esta evaluación ya fue enviada</h2>
        <p class="intro">Registramos su autoreporte de <strong>${esc(campania.nombre)}</strong>. Solo se permite una respuesta por periodo, para proteger la consistencia y su confidencialidad.</p>
        <div class="actions">
          <button type="button" class="btn btn-primary" data-go="tendencias">Ver mis tendencias</button>
          <button type="button" class="btn btn-secondary" data-go="inicio">Volver al inicio</button>
        </div>
      </div>`;
      bindCards(panel);
      return;
    }

    if (state.evalFase !== "quiz") {
      let participando = true;
      try {
        const cons = await api("/portal/consentimiento");
        participando = Boolean(cons.participando);
      } catch (_) {}
      if (!participando) {
        panel.innerHTML = `<div class="phase-screen">
          <h2>Necesitamos su consentimiento</h2>
          <p class="intro">Para enviar una evaluación debe aceptar el aviso de privacidad vigente.</p>
          <div class="actions">
            <button type="button" class="btn btn-primary" data-go="privacidad-colab">Ir a privacidad</button>
          </div>
        </div>`;
        bindCards(panel);
        return;
      }
      panel.innerHTML = `<div class="phase-screen">
        <p class="eyebrow">${esc(campania.nombre)}</p>
        <h2>Antes de comenzar</h2>
        <p class="intro">Esta evaluación busca entender la carga de trabajo y el clima de su equipo. Responda con sinceridad.</p>
        <ul class="checklist">
          <li>Sus respuestas son confidenciales y se procesan de forma anónima.</li>
          <li>Su líder no puede ver su cuestionario individual.</li>
          <li>Los resultados del equipo solo se publican si hay suficientes participaciones.</li>
          <li>Puede pausar su consentimiento en Privacidad cuando lo necesite.</li>
        </ul>
        <div class="actions">
          <button type="button" class="btn btn-primary" id="comenzar">Comenzar evaluación</button>
        </div>
      </div>`;
      $("comenzar").onclick = () => {
        state.evalFase = "quiz";
        pintarFase();
      };
      return;
    }

    panel.innerHTML = `<h2>${esc(campania.nombre)}</h2>
      <p class="intro">Por favor, responda con sinceridad. Sus respuestas son estrictamente confidenciales y se procesan de forma anónima para proteger su identidad.</p>
      <form id="f-enc">
        <div id="reactivos"></div>
        <div class="actions">
          <button class="btn btn-primary" type="submit" id="btn-enviar">Enviar evaluación</button>
        </div>
      </form>`;
    try {
      const r = await api(
        `/catalogos/instrumentos/${encodeURIComponent(campania.instrumento_id)}/versiones/${Number(campania.version_instrumento)}/reactivos`
      );
      const preguntas = Array.isArray(r.data) ? r.data : [];
      $("reactivos").innerHTML = preguntas
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
    } catch (e) {
      $("reactivos").innerHTML = `<p class="intro">${esc(e.message)}</p>`;
    }
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
            campania_id: campania.campania_id,
            respuestas,
          }),
        });
        state.evalFase = "exito";
        await pintarFase();
      } catch (e) {
        if (e.message === MENSAJES.YA_RESPONDIO) {
          state.evalFase = "intro";
          await pintarFase();
          return;
        }
        aviso(e.message, true);
      }
    };
  };

  await pintarFase();
}

async function panelTendencias(panel) {
  const data = await api("/portal/mis-evaluaciones");
  if (!data.data.length) {
    panel.innerHTML = `<h2>Mis tendencias</h2>
      <p class="empty">Aún no ha enviado evaluaciones. Cuando participe, verá aquí su historial personal.</p>
      <div class="actions"><button type="button" class="btn btn-primary" data-go="evaluacion">Ir a la evaluación</button></div>`;
    bindCards(panel);
    return;
  }
  panel.innerHTML = `<h2>Mis tendencias</h2>
    <p class="intro">Solo usted ve este historial. No se comparte con líderes ni se cruza con su identidad laboral.</p>
    <ul class="list-cards">${data.data
      .map(
        (x) => `<li><strong>${esc(formatFecha(x.fecha_respuesta))}</strong><br>
        <small>Promedio de su envío: ${esc(x.promedio ?? "—")}</small></li>`
      )
      .join("")}</ul>
    <div class="note">Las recomendaciones personalizadas automáticas se incorporarán cuando el programa de intervenciones esté activo. Si necesita ayuda ahora, use Solicitar apoyo.</div>`;
}

async function panelPrivacidadColab(panel) {
  const data = await api("/portal/consentimiento");
  panel.innerHTML = `<h2>Privacidad y consentimiento</h2>
    <p class="intro">Usted controla su participación. Pausar o revocar detiene nuevos envíos de evaluación.</p>
    <div class="note">${
      data.participando
        ? `Participación activa. Aviso vigente: ${esc(data.version_vigente)}.`
        : "Su participación está pausada o no hay consentimiento vigente."
    }</div>
    <h3>Quién puede ver información</h3>
    <ul class="checklist">
      <li>Su líder solo ve promedios del equipo, nunca su cuestionario.</li>
      <li>Esos promedios se ocultan si hay pocas respuestas (umbral de grupo).</li>
      <li>El auditor revisa accesos y consentimientos, no sus respuestas individuales.</li>
    </ul>
    <div class="actions">
      ${
        data.participando
          ? `<button type="button" class="btn btn-secondary" id="revocar">Pausar participación</button>`
          : `<button type="button" class="btn btn-primary" id="aceptar">Aceptar aviso y participar</button>`
      }
    </div>
    <h3>Historial</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>Aviso</th><th>Aceptado</th><th>Estado</th></tr></thead>
      <tbody>${(data.historial || [])
        .map(
          (f) => `<tr><td>${esc(f.version_consentimiento_id)}</td>
          <td>${esc(formatFecha(f.fecha_aceptacion))}</td>
          <td>${esc(f.estado === "ACEPTADO" ? "Activo" : "Revocado")}</td></tr>`
        )
        .join("")}</tbody>
    </table></div>`;
  const btnR = $("revocar");
  const btnA = $("aceptar");
  if (btnR) {
    btnR.onclick = async () => {
      await api("/portal/consentimiento", { method: "POST", body: JSON.stringify({ aceptar: false }) });
      await panelPrivacidadColab(panel);
    };
  }
  if (btnA) {
    btnA.onclick = async () => {
      await api("/portal/consentimiento", { method: "POST", body: JSON.stringify({ aceptar: true }) });
      await panelPrivacidadColab(panel);
    };
  }
}

async function panelApoyo(panel) {
  panel.innerHTML = `<h2>Solicitar apoyo</h2>
    <p class="intro">El mensaje se registra sin su nombre ni correo. Un especialista de bienestar podrá atenderlo de forma confidencial.</p>
    <form id="f-apoyo">
      <label for="mensaje">¿En qué podemos apoyar?</label>
      <textarea id="mensaje" name="mensaje" rows="5" required minlength="8" placeholder="Describa la situación con el detalle que le resulte cómodo."></textarea>
      <div class="actions"><button class="btn btn-primary" type="submit">Enviar solicitud</button></div>
    </form>`;
  $("f-apoyo").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      await api("/portal/soporte", {
        method: "POST",
        body: JSON.stringify({ mensaje: $("mensaje").value }),
      });
      panel.innerHTML = `<div class="phase-screen phase-ok">
        <h2>Solicitud enviada</h2>
        <p class="intro">Recibimos su mensaje. Un profesional de bienestar lo revisará sin asociarlo a su identidad laboral.</p>
        <div class="actions"><button type="button" class="btn btn-primary" data-go="inicio">Volver al inicio</button></div>
      </div>`;
      bindCards(panel);
    } catch (e) {
      aviso(e.message, true);
    }
  };
}

async function pintarAgregado(caja, unidadId, campania, kHint) {
  caja.innerHTML = `<p class="empty">Consultando resultados del grupo…</p>`;
  try {
    const data = await api(`/agregados/${encodeURIComponent(unidadId)}/${encodeURIComponent(campania.campania_id)}`);
    let nombres = {};
    try {
      const reactivos = await api(
        `/catalogos/instrumentos/${encodeURIComponent(campania.instrumento_id)}/versiones/${Number(campania.version_instrumento)}/reactivos`
      );
      nombres = Object.fromEntries((reactivos.data || []).map((r) => [r.reactivo_id, r.texto]));
    } catch (_) {}
    if (!data.visible) {
      caja.innerHTML = `<div class="aviso">Aún no hay suficientes respuestas para mostrar resultados de este equipo (mínimo ${esc(
        data.k || kHint || 5
      )} participaciones). Esta regla evita que alguien pueda ser identificado.</div>`;
      return;
    }
    const detalle = Object.entries(data.detalle || {});
    caja.innerHTML = `<div class="metrics">
        <div class="metric"><span>Participación del grupo</span><strong>${esc(data.total_respuestas)}</strong></div>
        <div class="metric"><span>Promedio general</span><strong>${esc(data.promedio_global)}</strong></div>
        <div class="metric"><span>Umbral de privacidad</span><strong>${esc(data.k)}</strong></div>
      </div>
      ${detalle
        .map(([id, valor]) => {
          const ancho = Math.max(0, Math.min(100, (Number(valor) / 5) * 100));
          return `<div class="bar-row"><p>${esc(nombres[id] || "Indicador")} · ${esc(valor)}</p>
            <div class="bar" aria-hidden="true"><i style="width:${ancho}%"></i></div></div>`;
        })
        .join("")}`;
  } catch (e) {
    caja.innerHTML = `<div class="aviso">${esc(e.message)}</div>`;
  }
}

async function panelResultados(panel) {
  const desk = await api("/portal/escritorio");
  const unidades = desk.unidades || [];
  const campanias = desk.campanias || [];
  if (!unidades.length || !campanias.length) {
    panel.innerHTML = `<h2>Resultados del equipo</h2>
      <p class="empty">No hay equipos o evaluaciones visibles para su perfil.</p>`;
    return;
  }
  const lider = state.me.perfil === "LIDER_TURNO";
  panel.innerHTML = `<h2>${lider ? "Resultados de su equipo" : "Métricas agregadas"}</h2>
    <p class="intro">${
      lider
        ? "Solo ve promedios de su equipo. Si el grupo es pequeño, no se muestra ninguna cifra."
        : "Consulte promedios por equipo y evaluación. Nunca se muestran respuestas individuales."
    }</p>
    <div class="filters">
      <div>
        <label for="u">Equipo</label>
        <select id="u">${opciones(unidades, "unidad_organizacional_id", "nombre")}</select>
      </div>
      <div>
        <label for="c">Evaluación</label>
        <select id="c">${opciones(campanias, "campania_id", "nombre")}</select>
      </div>
      <button type="button" class="btn btn-primary" id="ver">Actualizar</button>
    </div>
    <div id="resultado"></div>`;
  const cargar = () => {
    const campania = campanias.find((x) => x.campania_id === $("c").value) || campanias[0];
    return pintarAgregado($("resultado"), $("u").value, campania, desk.k);
  };
  $("ver").onclick = cargar;
  await cargar();
}

async function panelPrivacidadLider(panel) {
  const desk = await api("/portal/escritorio");
  panel.innerHTML = `<h2>Límites de privacidad</h2>
    <p class="intro">Su acceso está limitado a métricas de grupo. El sistema oculta resultados cuando hay menos de <strong>${esc(
      desk.k || 5
    )}</strong> respuestas en el equipo.</p>
    <ul class="checklist">
      <li>No puede ver evaluaciones individuales ni identidades.</li>
      <li>Use los agregados solo para detectar carga de trabajo del turno.</li>
      <li>Si el aviso de confidencialidad aparece, no hay excepción: hay que esperar más participaciones.</li>
    </ul>`;
}

async function panelPrivacidadAuditor(panel) {
  const cfg = await api("/portal/configuracion");
  panel.innerHTML = `<h2>Verificación de privacidad</h2>
    <p class="intro">Revise que el umbral de grupo y el aviso de privacidad estén vigentes. Los cambios de umbral los hace solo el administrador y quedan en la bitácora.</p>
    <div class="metrics">
      <div class="metric"><span>Umbral k</span><strong>${esc(cfg.k)}</strong></div>
      <div class="metric"><span>Aviso activo</span><strong>${esc(cfg.version_activa_consentimiento || "—")}</strong></div>
    </div>
    <p class="intro">Para auditar consultas de agregados, consentimientos y cambios de k, use la bitácora.</p>`;
}

async function panelOrganizacion(panel) {
  const desk = await api("/portal/escritorio");
  const tipo = (t) =>
    t === "NOM035" ? "Factores de riesgo psicosocial" : t === "CLIMA" ? "Clima laboral" : t || "Instrumento";
  panel.innerHTML = `<h2>Instrumentos y equipos</h2>
    <p class="intro">Catálogos para configurar evaluaciones y analizar departamentos. Los instrumentos definen el cuestionario; las campañas lo aplican a un equipo.</p>
    <h3>Equipos</h3>
    <ul class="list-cards">${(desk.unidades || []).map((x) => `<li>${esc(x.nombre)}</li>`).join("") || "<li>No hay equipos</li>"}</ul>
    <h3>Evaluaciones</h3>
    <ul class="list-cards">${
      (desk.campanias || [])
        .map((x) => `<li>${esc(x.nombre)}<br><small>${esc(formatDia(x.fecha_inicio))} — ${esc(formatDia(x.fecha_fin))}</small></li>`)
        .join("") || "<li>No hay evaluaciones</li>"
    }</ul>
    <h3>Instrumentos</h3>
    <ul class="list-cards">${
      (desk.instrumentos || [])
        .map((x) => `<li>${esc(x.nombre)}<br><small>${esc(tipo(x.tipo))}</small></li>`)
        .join("") || "<li>No hay instrumentos</li>"
    }</ul>`;
}

async function panelCuentas(panel) {
  const data = await api("/portal/cuentas");
  panel.innerHTML = `<h2>Cuentas y perfiles</h2>
    <p class="intro">Administración de acceso. Esta lista no se cruza con respuestas de encuesta.</p>
    <h3>Perfiles</h3>
    <ul class="list-cards">${(data.perfiles || [])
      .map((p) => `<li><strong>${esc(p.nombre)}</strong><br><small>Nivel de acceso ${esc(p.nivel_acceso)}</small></li>`)
      .join("")}</ul>
    <h3>Cuentas</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>Correo</th><th>Perfil</th><th>Nivel</th><th>Estado</th><th>Último acceso</th></tr></thead>
      <tbody>${(data.usuarios || [])
        .map(
          (u) => `<tr>
            <td>${esc(u.correo)}</td>
            <td>${esc(u.perfil_nombre)}</td>
            <td>${esc(u.nivel_acceso)}</td>
            <td>${u.activo ? "Activa" : "Inactiva"}</td>
            <td>${esc(u.fecha_ultimo_acceso ? formatFecha(u.fecha_ultimo_acceso) : "—")}</td>
          </tr>`
        )
        .join("")}</tbody>
    </table></div>
    <div class="note">El alta de nuevas cuentas en este producto mínimo se realiza con el esquema institucional. Aquí se consultan perfiles y accesos vigentes.</div>`;
}

async function panelActividad(panel) {
  const data = await api("/auditoria");
  const filas = Array.isArray(data.data) ? data.data : [];
  panel.innerHTML = `<h2>Bitácora de auditoría</h2>
    <p class="intro">Acciones críticas: inicios de sesión, envíos, consultas de agregados, historial de consentimiento y cambios del umbral de privacidad.</p>
    ${
      filas.length
        ? `<div class="table-wrap"><table>
      <thead><tr><th>Actividad</th><th>Ámbito</th><th>Cuenta</th><th>Perfil</th><th>Resultado</th><th>Fecha</th></tr></thead>
      <tbody>${filas
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
    </table></div>`
        : `<p class="empty">Todavía no hay actividad registrada.</p>`
    }`;
}

async function panelConsentimiento(panel) {
  panel.innerHTML = `<h2>Historial de consentimientos</h2>
    <p class="intro">Audite aceptaciones y revocaciones por código de participante, sin identidad laboral.</p>
    <form id="f-cons">
      <label for="codigo">Código de participante</label>
      <input id="codigo" name="codigo" required placeholder="Ingrese el código asignado" autocomplete="off">
      <div class="actions"><button class="btn btn-primary" type="submit">Consultar</button></div>
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
        caja.innerHTML = `<p class="empty">No hay registros para este código.</p>`;
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
      caja.innerHTML = `<p class="intro">${esc(e.message)}</p>`;
    }
  };
}

async function panelSoporte(panel) {
  const data = await api("/portal/soporte");
  const filas = data.data || [];
  panel.innerHTML = `<h2>Solicitudes de apoyo</h2>
    <p class="intro">Mensajes de colaboradores sin nombre, correo ni identificador laboral.</p>
    ${
      filas.length
        ? `<ul class="list-cards">${filas
            .map((s) => `<li><strong>${esc(formatFecha(s.fecha))}</strong><br>${esc(s.mensaje)}</li>`)
            .join("")}</ul>`
        : `<p class="empty">No hay solicitudes por ahora.</p>`
    }`;
}

async function panelPrivacidad(panel) {
  const cfg = await api("/portal/configuracion");
  panel.innerHTML = `<h2>Parámetros globales</h2>
    <p class="intro">Defina el umbral mínimo de grupo (k) y la versión activa del aviso de privacidad. Cada cambio queda en la bitácora.</p>
    <form id="fk">
      <label for="k">Umbral de privacidad (respuestas mínimas del equipo)</label>
      <input id="k" name="k" type="number" min="2" max="50" value="${esc(cfg.k)}" required>
      <label for="ver">Versión activa del aviso</label>
      <select id="ver" name="version">${(cfg.versiones || [])
        .map(
          (v) =>
            `<option value="${esc(v.version_consentimiento_id)}" ${
              v.version_consentimiento_id === cfg.version_activa_consentimiento ? "selected" : ""
            }>${esc(v.version_consentimiento_id)}</option>`
        )
        .join("")}</select>
      <div class="actions"><button class="btn btn-primary" type="submit">Guardar</button></div>
    </form>`;
  $("fk").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      await api("/portal/configuracion", {
        method: "PATCH",
        body: JSON.stringify({
          k: Number($("k").value),
          version_activa_consentimiento: $("ver").value,
        }),
      });
      panel.innerHTML = `<div class="phase-screen phase-ok"><h2>Parámetros actualizados</h2>
        <p class="intro">El umbral de grupo y el aviso activo quedaron guardados.</p>
        <div class="actions"><button type="button" class="btn btn-primary" id="volver">Seguir editando</button></div></div>`;
      $("volver").onclick = () => panelPrivacidad(panel);
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
