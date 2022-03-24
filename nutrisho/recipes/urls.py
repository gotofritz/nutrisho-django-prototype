from django.urls import path

from .views import home, recipe

app_name = "recipes"
urlpatterns = [
    path("", home, name="home"),
    path("<int:recipe_id>/", recipe, name="recipe"),
]
