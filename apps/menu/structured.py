from django.urls import reverse
from django.utils.translation import gettext


def restaurant_schema(request, restaurant, dishes):
    url = request.build_absolute_uri(reverse("restaurant_detail", args=[restaurant.pk]))
    return {
        "@context": "https://schema.org",
        "@type": "Restaurant",
        "name": restaurant.name,
        "url": url,
        "servesCuisine": gettext(restaurant.cuisine) if restaurant.cuisine else "",
        "address": {"@type": "PostalAddress", "streetAddress": restaurant.address},
        "hasMenu": {
            "@type": "Menu", "url": url,
            "hasMenuItem": [
                {
                    "@type": "MenuItem", "name": dish.localized_name,
                    "description": dish.localized_description,
                    "offers": {"@type": "Offer", "price": str(dish.price), "priceCurrency": "UZS"},
                }
                for dish in dishes
            ],
        },
    }
