package classifier;

import util.InputValidator;

public final class ClassifierService {
    private final RegexClassifier regex = new RegexClassifier();
    private final NlpClassifier nlp = new NlpClassifier();

    public ClassificationResult clasificar(String nombre, String apellido, String texto) {
        InputValidator.validar(nombre, apellido, texto);
        ClassificationResult r = regex.classify(texto);
        ClassificationResult n = nlp.classify(texto);
        return new ClassificationResult(
                r.regex(),
                n.nlp(),
                r.puntajesRegex(),
                n.puntajesNlp(),
                n.textoProcesado()
        );
    }
}
