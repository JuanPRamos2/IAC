package classifier;

import java.util.List;
import java.util.Map;

public final class NlpClassifier {
    private static final Map<CloudModel, List<String>> STEMS = Map.of(
            CloudModel.IAAS, List.of("maquin", "virtual", "almacen", "red", "instal", "disco", "linux", "ec2", "instanci", "infraestructur", "so"),
            CloudModel.PAAS, List.of("despleg", "plataform", "administr"),
            CloudModel.SAAS, List.of("correo", "navegador", "suscrip"),
            CloudModel.FAAS, List.of("funcion", "event", "imagen", "serverless")
    );

    public ClassificationResult classify(String texto) {
        Map<CloudModel, Integer> scores = ClassificationResult.vacio();
        List<String> tokens = TextPreprocessor.tokens(texto);
        for (var entry : STEMS.entrySet()) {
            for (String root : entry.getValue()) {
                int hits = 0;
                for (String token : tokens) {
                    if (token.startsWith(root) || root.startsWith(token)) {
                        hits++;
                    }
                }
                if (hits > 0) {
                    scores.merge(entry.getKey(), hits, Integer::sum);
                }
            }
        }
        if (texto.toLowerCase().contains("sin administrar servidores")) {
            scores.merge(CloudModel.PAAS, 3, Integer::sum);
            scores.put(CloudModel.IAAS, 0);
        }
        if (texto.toLowerCase().contains("funci") && texto.toLowerCase().contains("sub")) {
            scores.merge(CloudModel.FAAS, 2, Integer::sum);
            scores.put(CloudModel.IAAS, 0);
        }
        CloudModel model = Scoring.winner(scores);
        return new ClassificationResult(
                CloudModel.INDETERMINADO,
                model,
                ClassificationResult.vacio(),
                scores,
                TextPreprocessor.procesado(texto)
        );
    }
}
