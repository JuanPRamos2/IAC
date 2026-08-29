package ui;

import classifier.ClassificationResult;
import classifier.CloudModel;
import classifier.ClassifierService;
import util.ValidationException;

import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JTextArea;
import javax.swing.JTextField;
import javax.swing.border.EmptyBorder;
import java.awt.BorderLayout;
import java.awt.GridLayout;

public final class ClassifierWindow extends JFrame {
    private final JTextField nombre = new JTextField();
    private final JTextField apellido = new JTextField();
    private final JTextArea texto = new JTextArea(6, 40);
    private final JTextArea salida = new JTextArea(12, 40);
    private final ClassifierService service = new ClassifierService();

    public ClassifierWindow() {
        super("Clasificador Cloud");
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        JPanel form = new JPanel(new GridLayout(0, 1, 6, 6));
        form.setBorder(new EmptyBorder(12, 12, 12, 12));
        form.add(new JLabel("Nombre"));
        form.add(nombre);
        form.add(new JLabel("Apellido"));
        form.add(apellido);
        form.add(new JLabel("Descripción del servicio"));
        form.add(new JScrollPane(texto));
        JButton boton = new JButton("Clasificar");
        boton.addActionListener(e -> clasificar());
        form.add(boton);
        salida.setEditable(false);
        add(form, BorderLayout.NORTH);
        add(new JScrollPane(salida), BorderLayout.CENTER);
        pack();
        setLocationRelativeTo(null);
    }

    private void clasificar() {
        try {
            ClassificationResult result = service.clasificar(nombre.getText(), apellido.getText(), texto.getText());
            StringBuilder sb = new StringBuilder();
            sb.append("Regex: ").append(result.regex().etiqueta()).append('\n');
            appendScores(sb, result.puntajesRegex());
            sb.append("NLP: ").append(result.nlp().etiqueta()).append('\n');
            appendScores(sb, result.puntajesNlp());
            sb.append("Procesado: ").append(result.textoProcesado()).append('\n');
            salida.setText(sb.toString());
        } catch (ValidationException ex) {
            salida.setText(ex.getMessage());
        }
    }

    private static void appendScores(StringBuilder sb, java.util.Map<CloudModel, Integer> puntajes) {
        for (CloudModel model : new CloudModel[] {CloudModel.IAAS, CloudModel.PAAS, CloudModel.SAAS, CloudModel.FAAS}) {
            sb.append("  ").append(model.etiqueta()).append(": ").append(puntajes.getOrDefault(model, 0)).append('\n');
        }
    }
}
