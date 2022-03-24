from django.urls import path

from .views import home, recipe

urlpatterns = [
    path("", home, name="home"),
    path("<int:recipe_id>/", recipe, name="recipe"),
]
