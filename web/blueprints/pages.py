"""Páginas HTML del sitio."""

from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def inicio():
    return render_template("index.html")


@pages_bp.get("/clasificador")
def clasificador():
    return render_template("clasificador.html")


@pages_bp.get("/acerca")
def acerca():
    return render_template("acerca.html")
