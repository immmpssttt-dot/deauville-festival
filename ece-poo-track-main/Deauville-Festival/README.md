## Modèles POO (Étape 07)

- **Venue** : Salle de spectacle (slug, nom, capacité, adresse).
- **Artist** : Artiste intervenant au festival (slug, nom).
- **Performance** : Spectacle ou atelier.
  - *Attributs* : titre, type (`kind`), lieu, heure de début (`start_iso`), durée, rôles (artiste, hôte, intervenant, troupes, participants).
  - *Propriétés (`@property`)* : `start` (datetime), `end` (datetime), `festival_day` (date), `id` (identifiant unique), `places_left` (places restantes).
  - *Méthodes* : `involves(artist_slug)`, `to_dict()`.