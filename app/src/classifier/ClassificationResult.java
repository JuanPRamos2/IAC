package classifier;

import java.util.EnumMap;
import java.util.Map;

public final class ClassificationResult {
    private final CloudModel regex;
    private final CloudModel nlp;
    private final Map<CloudModel, Integer> puntajesRegex;
    private final Map<CloudModel, Integer> puntajesNlp;
    private final String textoProcesado;

    public ClassificationResult(
            CloudModel regex,
            CloudModel nlp,
            Map<CloudModel, Integer> puntajesRegex,
            Map<CloudModel, Integer> puntajesNlp,
            String textoProcesado) {
        this.regex = regex;
        this.nlp = nlp;
        this.puntajesRegex = puntajesRegex;
        this.puntajesNlp = puntajesNlp;
        this.textoProcesado = textoProcesado;
    }

    public CloudModel regex() {
        return regex;
    }

    public CloudModel nlp() {
        return nlp;
    }

    public Map<CloudModel, Integer> puntajesRegex() {
        return puntajesRegex;
    }

    public Map<CloudModel, Integer> puntajesNlp() {
        return puntajesNlp;
    }

    public String textoProcesado() {
        return textoProcesado;
    }

    public static Map<CloudModel, Integer> vacio() {
        EnumMap<CloudModel, Integer> map = new EnumMap<>(CloudModel.class);
        map.put(CloudModel.IAAS, 0);
        map.put(CloudModel.PAAS, 0);
        map.put(CloudModel.SAAS, 0);
        map.put(CloudModel.FAAS, 0);
        return map;
    }
}
