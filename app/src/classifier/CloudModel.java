package classifier;

public enum CloudModel {
    IAAS("IaaS"),
    PAAS("PaaS"),
    SAAS("SaaS"),
    FAAS("FaaS"),
    INDETERMINADO("Indeterminado");

    private final String etiqueta;

    CloudModel(String etiqueta) {
        this.etiqueta = etiqueta;
    }

    public String etiqueta() {
        return etiqueta;
    }

    public static CloudModel fromEtiqueta(String etiqueta) {
        for (CloudModel model : values()) {
            if (model.etiqueta.equalsIgnoreCase(etiqueta)) {
                return model;
            }
        }
        return INDETERMINADO;
    }
}
