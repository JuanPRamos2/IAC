package classifier;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class TextPreprocessor {
    private static final Set<String> STOPWORDS = Set.of(
            "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "y", "o",
            "a", "en", "con", "por", "para", "que", "se", "su", "sus", "mi", "mis",
            "tu", "tus", "al", "lo", "le", "les", "es", "son", "ser", "como", "cada", "vez"
    );

    private TextPreprocessor() {}

    public static String stripAccents(String value) {
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFD);
        return normalized.replaceAll("\\p{M}+", "");
    }

    public static String stem(String token) {
        String t = token;
        t = t.replaceAll("(aciones|acion)$", "acion");
        t = t.replaceAll("(amiento|imentos)$", "ament");
        t = t.replaceAll("(ando|iendo|ar|er|ir)$", "");
        t = t.replaceAll("es$", "");
        if (t.endsWith("s") && t.length() > 3) {
            t = t.substring(0, t.length() - 1);
        }
        return t;
    }

    public static List<String> tokens(String texto) {
        String clean = stripAccents(texto.toLowerCase(Locale.ROOT)).replaceAll("[^\\p{L}\\p{N}]+", " ");
        List<String> out = new ArrayList<>();
        for (String raw : clean.split("\\s+")) {
            if (raw.length() <= 1 || STOPWORDS.contains(raw)) {
                continue;
            }
            out.add(stem(raw));
        }
        return out;
    }

    public static String procesado(String texto) {
        return String.join(" ", tokens(texto));
    }
}
