from django.urls import path

from .views import home, recipe, recipe_edit

app_name = "recipes"
urlpatterns = [
    path("", home, name="home"),
    path("<int:recipe_id>/", recipe, name="recipe"),
    path("<int:recipe_id>/edit", recipe_edit, name="edit"),
    path("<int:recipe_id>/update", recipe, name="update"),
]
