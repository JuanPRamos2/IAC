package classifier;

import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

final class Scoring {
    private Scoring() {}

    static CloudModel winner(Map<CloudModel, Integer> scores) {
        CloudModel best = CloudModel.INDETERMINADO;
        int bestScore = 0;
        boolean tie = false;
        for (CloudModel model : List.of(CloudModel.IAAS, CloudModel.PAAS, CloudModel.SAAS, CloudModel.FAAS)) {
            int value = scores.getOrDefault(model, 0);
            if (value > bestScore) {
                best = model;
                bestScore = value;
                tie = false;
            } else if (value == bestScore && value > 0) {
                tie = true;
            }
        }
        if (bestScore <= 0 || tie) {
            return CloudModel.INDETERMINADO;
        }
        return best;
    }

    static void applyPolicy(String texto, Map<CloudModel, Integer> scores) {
        if (Pattern.compile("sin administrar servidores", Pattern.CASE_INSENSITIVE).matcher(texto).find()) {
            scores.put(CloudModel.IAAS, 0);
        }
        if (Pattern.compile("funci[oó]n", Pattern.CASE_INSENSITIVE).matcher(texto).find()
                && texto.toLowerCase().contains("sub")) {
            scores.put(CloudModel.IAAS, 0);
        }
    }
}
