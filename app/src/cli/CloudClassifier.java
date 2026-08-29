package cli;

import classifier.ClassificationResult;
import classifier.CloudModel;
import classifier.ClassifierService;
import util.ValidationException;

import java.util.Scanner;

public final class CloudClassifier {
    public static void main(String[] args) {
        ClassifierService service = new ClassifierService();
        if (args.length >= 1) {
            try {
                imprimir(service.clasificar("CLI", "Usuario", String.join(" ", args)));
            } catch (ValidationException ex) {
                System.err.println(ex.getMessage());
                System.exit(1);
            }
            return;
        }

        Scanner scanner = new Scanner(System.in);
        System.out.println("Clasificador Cloud (IaaS / PaaS / SaaS / FaaS)");
        System.out.print("Nombre: ");
        String nombre = scanner.nextLine();
        System.out.print("Apellido: ");
        String apellido = scanner.nextLine();
        System.out.print("Descripción: ");
        String texto = scanner.nextLine();
        try {
            imprimir(service.clasificar(nombre, apellido, texto));
        } catch (ValidationException ex) {
            System.err.println(ex.getMessage());
            System.exit(1);
        }
    }

    private static void imprimir(ClassificationResult result) {
        System.out.println("Regex: " + result.regex().etiqueta());
        imprimirPuntajes(result.puntajesRegex());
        System.out.println("NLP:   " + result.nlp().etiqueta());
        imprimirPuntajes(result.puntajesNlp());
        System.out.println("Texto procesado: " + result.textoProcesado());
    }

    private static void imprimirPuntajes(java.util.Map<CloudModel, Integer> puntajes) {
        for (CloudModel model : new CloudModel[] {CloudModel.IAAS, CloudModel.PAAS, CloudModel.SAAS, CloudModel.FAAS}) {
            System.out.printf("  %s: %d%n", model.etiqueta(), puntajes.getOrDefault(model, 0));
        }
    }
}
