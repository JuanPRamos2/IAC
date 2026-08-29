/**
 * Clasificador IaaS / PaaS / SaaS / FaaS (regex + NLP básico).
 * Misma política que app/src/classifier en Java.
 */
(function (global) {
  const MODELS = ["IaaS", "PaaS", "SaaS", "FaaS"];

  const STOPWORDS = new Set(
    "el la los las un una unos unas de del y o a en con por para que se su sus mi mis tu tus al lo le les es son ser un como cada vez".split(
      " "
    )
  );

  const REGEX_RULES = [
    { model: "IaaS", re: /m[aá]quinas?\s+virtuales?/i, w: 3 },
    { model: "IaaS", re: /\bvm\b/i, w: 2 },
    { model: "IaaS", re: /almacenamiento/i, w: 2 },
    { model: "IaaS", re: /\bred(?:es)?\b/i, w: 2 },
    { model: "IaaS", re: /sistemas?\s+operativos?|\bso\b/i, w: 2 },
    { model: "IaaS", re: /\bec2\b|instancias?/i, w: 3 },
    { model: "IaaS", re: /discos?/i, w: 2 },
    { model: "IaaS", re: /linux/i, w: 2 },
    { model: "IaaS", re: /infraestructura/i, w: 2 },
    { model: "PaaS", re: /desplegar/i, w: 3 },
    { model: "PaaS", re: /sin administrar servidores/i, w: 4 },
    { model: "PaaS", re: /plataforma/i, w: 3 },
    { model: "SaaS", re: /correo/i, w: 3 },
    { model: "SaaS", re: /navegador/i, w: 3 },
    { model: "SaaS", re: /suscripci[oó]n/i, w: 3 },
    { model: "FaaS", re: /funci[oó]n(?:es)?/i, w: 3 },
    { model: "FaaS", re: /cada vez que/i, w: 2 },
    { model: "FaaS", re: /suba una imagen|subir una imagen/i, w: 3 },
    { model: "FaaS", re: /evento/i, w: 2 },
    { model: "FaaS", re: /serverless/i, w: 3 },
  ];

  const NLP_STEMS = {
    IaaS: ["maquin", "virtual", "almacen", "red", "instal", "disco", "linux", "ec2", "instanci", "infraestructur", "so"],
    PaaS: ["despleg", "plataform", "administr"],
    SaaS: ["correo", "navegador", "suscrip"],
    FaaS: ["funcion", "event", "imagen", "serverless"],
  };

  function emptyScores() {
    return { IaaS: 0, PaaS: 0, SaaS: 0, FaaS: 0 };
  }

  function winner(scores) {
    const entries = MODELS.map((m) => [m, scores[m]]);
    entries.sort((a, b) => b[1] - a[1]);
    if (entries[0][1] <= 0 || entries[0][1] === entries[1][1]) return "Indeterminado";
    return entries[0][0];
  }

  function applyPolicy(text, scores) {
    const lower = text.toLowerCase();
    if (/sin administrar servidores/i.test(text)) {
      scores.IaaS = 0;
    }
    if (/funci[oó]n/i.test(text) && /sub/i.test(lower)) {
      scores.IaaS = Math.min(scores.IaaS, 0);
    }
    return scores;
  }

  function classifyRegex(text) {
    const scores = emptyScores();
    for (const rule of REGEX_RULES) {
      if (rule.re.test(text)) scores[rule.model] += rule.w;
    }
    applyPolicy(text, scores);
    return { modelo: winner(scores), puntajes: scores };
  }

  function stripAccents(value) {
    return value.normalize("NFD").replace(/\p{M}/gu, "");
  }

  function stem(token) {
    let t = token;
    t = t.replace(/(aciones|acion|aciones)$/u, "acion");
    t = t.replace(/(amiento|imentos)$/u, "ament");
    t = t.replace(/(ando|iendo|ar|er|ir)$/u, "");
    t = t.replace(/es$/u, "");
    if (t.endsWith("s") && t.length > 3) t = t.slice(0, -1);
    return t;
  }

  function preprocess(text) {
    const clean = stripAccents(text.toLowerCase()).replace(/[^\p{L}\p{N}]+/gu, " ");
    return clean
      .split(/\s+/)
      .filter(Boolean)
      .filter((tok) => !STOPWORDS.has(tok) && tok.length > 1)
      .map(stem);
  }

  function classifyNlp(text) {
    const scores = emptyScores();
    const tokens = preprocess(text);
    for (const model of MODELS) {
      for (const root of NLP_STEMS[model]) {
        const hits = tokens.filter((tok) => tok.startsWith(root) || root.startsWith(tok)).length;
        if (hits) scores[model] += hits;
      }
    }
    if (/sin administrar servidores/i.test(text)) {
      scores.PaaS += 3;
      scores.IaaS = 0;
    }
    if (/funci[oó]n/i.test(text) && /sub/i.test(text.toLowerCase())) {
      scores.FaaS += 2;
      scores.IaaS = 0;
    }
    return { modelo: winner(scores), puntajes: scores };
  }

  function classify(text) {
    return {
      regex: classifyRegex(text),
      nlp: classifyNlp(text),
      textoProcesado: preprocess(text).join(" "),
    };
  }

  function validate(nombre, apellido, texto) {
    if (!nombre || !nombre.trim()) return "El nombre es obligatorio.";
    if (!apellido || !apellido.trim()) return "El apellido es obligatorio.";
    if (!texto || texto.trim().length < 8) return "El texto debe tener al menos 8 caracteres.";
    return null;
  }

  global.IacClassifier = {
    MODELS,
    classify,
    classifyRegex,
    classifyNlp,
    preprocess,
    validate,
  };
})(typeof window !== "undefined" ? window : globalThis);
