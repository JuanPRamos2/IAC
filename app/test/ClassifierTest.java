import classifier.ClassificationResult;
import classifier.ClassifierService;
import util.ValidationException;

public final class ClassifierTest {
    public static void main(String[] args) {
        ClassifierService service = new ClassifierService();
        String[][] cases = {
                {"Máquinas virtuales, almacenamiento y redes para instalar mi propio SO.", "IaaS"},
                {"Desplegar una aplicación web sin administrar servidores ni sistemas operativos.", "PaaS"},
                {"Correo electrónico en el navegador con suscripción mensual.", "SaaS"},
                {"Ejecutar una función cada vez que un usuario suba una imagen.", "FaaS"},
                {"Instancias EC2, discos persistentes y red privada para instalar Linux.", "IaaS"}
        };
        int failed = 0;
        for (String[] row : cases) {
            ClassificationResult result = service.clasificar("Ana", "Perez", row[0]);
            if (!row[1].equals(result.regex().etiqueta()) || !row[1].equals(result.nlp().etiqueta())) {
                System.err.printf("FALLA \"%s\" regex=%s nlp=%s esperado=%s%n",
                        row[0], result.regex().etiqueta(), result.nlp().etiqueta(), row[1]);
                failed++;
            }
        }
        try {
            service.clasificar("", "Perez", "texto de prueba suficientemente largo");
            System.err.println("FALLA: debía rechazar nombre vacío");
            failed++;
        } catch (ValidationException ex) {
            if (!ex.getMessage().contains("nombre")) {
                System.err.println("FALLA mensaje de validación: " + ex.getMessage());
                failed++;
            }
        }
        if (failed > 0) {
            System.exit(1);
        }
        System.out.println("OK " + cases.length + " casos Java");
    }
}
