package classifier;

import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

public final class RegexClassifier {
    private record Rule(CloudModel model, Pattern pattern, int weight) {}

    private static final List<Rule> RULES = List.of(
            new Rule(CloudModel.IAAS, Pattern.compile("m[aá]quinas?\\s+virtuales?", Pattern.CASE_INSENSITIVE), 3),
            new Rule(CloudModel.IAAS, Pattern.compile("\\bvm\\b", Pattern.CASE_INSENSITIVE), 2),
            new Rule(CloudModel.IAAS, Pattern.compile("almacenamiento", Pattern.CASE_INSENSITIVE), 2),
            new Rule(CloudModel.IAAS, Pattern.compile("\\bred(?:es)?\\b", Pattern.CASE_INSENSITIVE), 2),
            new Rule(CloudModel.IAAS, Pattern.compile("sistemas?\\s+operativos?|\\bso\\b", Pattern.CASE_INSENSITIVE), 2),
            new Rule(CloudModel.IAAS, Pattern.compile("\\bec2\\b|instancias?", Pattern.CASE_INSENSITIVE), 3),
            new Rule(CloudModel.IAAS, Pattern.compile("discos?", Pattern.CASE_INSENSITIVE), 2),
            new Rule(CloudModel.IAAS, Pattern.compile("linux", Pattern.CASE_INSENSITIVE), 2),
            new Rule(CloudModel.IAAS, Pattern.compile("infraestructura", Pattern.CASE_INSENSITIVE), 2),
            new Rule(CloudModel.PAAS, Pattern.compile("desplegar", Pattern.CASE_INSENSITIVE), 3),
            new Rule(CloudModel.PAAS, Pattern.compile("sin administrar servidores", Pattern.CASE_INSENSITIVE), 4),
            new Rule(CloudModel.PAAS, Pattern.compile("plataforma", Pattern.CASE_INSENSITIVE), 3),
            new Rule(CloudModel.SAAS, Pattern.compile("correo", Pattern.CASE_INSENSITIVE), 3),
            new Rule(CloudModel.SAAS, Pattern.compile("navegador", Pattern.CASE_INSENSITIVE), 3),
            new Rule(CloudModel.SAAS, Pattern.compile("suscripci[oó]n", Pattern.CASE_INSENSITIVE), 3),
            new Rule(CloudModel.FAAS, Pattern.compile("funci[oó]n(?:es)?", Pattern.CASE_INSENSITIVE), 3),
            new Rule(CloudModel.FAAS, Pattern.compile("cada vez que", Pattern.CASE_INSENSITIVE), 2),
            new Rule(CloudModel.FAAS, Pattern.compile("suba una imagen|subir una imagen", Pattern.CASE_INSENSITIVE), 3),
            new Rule(CloudModel.FAAS, Pattern.compile("evento", Pattern.CASE_INSENSITIVE), 2),
            new Rule(CloudModel.FAAS, Pattern.compile("serverless", Pattern.CASE_INSENSITIVE), 3)
    );

    public ClassificationResult classify(String texto) {
        Map<CloudModel, Integer> scores = ClassificationResult.vacio();
        for (Rule rule : RULES) {
            if (rule.pattern.matcher(texto).find()) {
                scores.merge(rule.model, rule.weight, Integer::sum);
            }
        }
        Scoring.applyPolicy(texto, scores);
        CloudModel model = Scoring.winner(scores);
        return new ClassificationResult(model, CloudModel.INDETERMINADO, scores, ClassificationResult.vacio(), texto);
    }
}
