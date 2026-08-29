package ui;

import javax.swing.SwingUtilities;

public final class CloudClassifierApp {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> new ClassifierWindow().setVisible(true));
    }
}
