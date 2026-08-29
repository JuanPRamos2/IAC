package util;

public final class InputValidator {
    private InputValidator() {}

    public static void validar(String nombre, String apellido, String texto) {
        if (nombre == null || nombre.isBlank()) {
            throw new ValidationException("El nombre es obligatorio.");
        }
        if (apellido == null || apellido.isBlank()) {
            throw new ValidationException("El apellido es obligatorio.");
        }
        if (texto == null || texto.trim().length() < 8) {
            throw new ValidationException("El texto debe tener al menos 8 caracteres.");
        }
    }
}
