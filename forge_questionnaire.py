# -*- coding: utf-8 -*-
"""
FORGE — Questionnaire "Capital récupération" (V8) — portage Python
===================================================================

Portage fidèle de la version web V8 : même jeu de questions, même pondération
scientifique, mêmes red flags, même persona/CRM et mêmes conseils par domaine.

Deux usages :
  1) Application interactive (recommandé) :
        pip install streamlit matplotlib
        streamlit run forge_questionnaire.py
     → questionnaire pas-à-pas, radar 6 axes, restitution, persona en coulisse.

  2) Moteur seul (sans interface) : importez les fonctions
        from forge_questionnaire import compute_scores, red_flags, persona, build_crm
     ou lancez une démo en console :
        python forge_questionnaire.py        (si streamlit n'est pas lancé)

Le moteur (données + fonctions de calcul) n'a AUCUNE dépendance : il est
importable tel quel dans un back-end (API, pipeline CRM, etc.).
Streamlit et matplotlib ne sont nécessaires que pour l'interface / le radar.

Note scientifique : pondérations calibrées sur la littérature (PSQI, WHO-5,
PSS, SRSS, OMS 2020, NOVA…), à revérifier/calibrer sur données réelles avant
toute publication. Ce bilan n'est pas un diagnostic médical.
"""

from __future__ import annotations
import math

# =====================================================================
#  1. DONNÉES — questions, conseils, libellés
# =====================================================================

PAGES = [
    {"id": "profil", "n": "01", "sec": "Habitudes de vie", "title": "Votre quotidien.",
     "intro": "Pour situer votre profil et personnaliser vos conseils.",
     "qs": [
         {"id": "metier", "type": "text", "optional": True, "l": "Quel est votre métier ?", "hint": "Facultatif."},
         {"id": "travail", "type": "choice", "l": "Au travail, vous êtes plutôt…",
          "o": [("sed", "Sédentaire (assis)"), ("mixte", "Mixte"), ("phys", "Physique / debout")]},
         {"id": "objectif", "type": "choice", "l": "Votre priorité n°1 en ce moment ?",
          "o": [("energie", "Retrouver de l'énergie et mieux dormir"), ("souffler", "Souffler, relâcher la pression"),
                ("douleur", "Réduire mes douleurs et tensions"), ("recup_sport", "Mieux récupérer après le sport"),
                ("force", "Gagner en force et en forme"), ("longevite", "Préserver ma vitalité et optimiser ma longévité"),
                ("rehab", "Revenir d'une blessure")]},
         {"id": "obj_sec", "type": "multi", "optional": True, "l": "D'autres objectifs secondaires ? (plusieurs possibles)",
          "o": [("energie", "Retrouver de l'énergie et mieux dormir"), ("souffler", "Souffler, relâcher la pression"),
                ("douleur", "Réduire mes douleurs et tensions"), ("recup_sport", "Mieux récupérer après le sport"),
                ("force", "Gagner en force et en forme"), ("longevite", "Préserver ma vitalité et optimiser ma longévité"),
                ("rehab", "Revenir d'une blessure")]},
         {"id": "compet", "type": "choice", "l": "Pratiquez-vous un sport en compétition ?",
          "o": [("comp_reg", "Oui, régulièrement"), ("comp_occ", "Oui, parfois"),
                ("loisir", "Non, en loisir"), ("nonsport", "Je ne fais pas de sport")]},
         {"id": "freq", "type": "choice", "l": "Séances de sport / activité physique par semaine ?",
          "o": [("f0", "0"), ("f12", "1–2"), ("f34", "3–4"), ("f5", "5 et +")]},
         {"id": "phase", "type": "choice", "optional": True, "hint": "Facultatif.",
          "l": "Si vous vous entraînez, dans quelle phase êtes-vous ?",
          "o": [("dev", "Développement / renforcement"), ("intersaison", "Intersaison"), ("endurance", "Endurance / cardio"),
                ("compet", "Compétition"), ("entretien", "Entretien"), ("reprise", "Reprise / réhab"),
                ("blesse", "Blessé (en cours de soin)"), ("na", "Pas concerné")]},
     ]},
    {"id": "sommeil", "n": "02", "sec": "Sommeil", "title": "Votre sommeil.",
     "intro": "Le socle de la récupération : régularité, durée, qualité.",
     "qs": [
         {"id": "s_reg", "type": "choice", "sci": "MCTQ*", "l": "Vos horaires de coucher / lever sont-ils réguliers ?",
          "o": [("tres", "Très réguliers"), ("plutot", "Plutôt régulier"), ("assez", "Assez variables"), ("var", "Très variables")]},
         {"id": "s_duree", "type": "choice", "sci": "PSQI*", "l": "Combien d'heures dormez-vous réellement par nuit ?",
          "o": [("d5", "< 5 h"), ("d56", "5–6 h"), ("d67", "6–7 h"), ("d78", "7–8 h"), ("d8", "> 8 h")]},
         {"id": "s_qual", "type": "scale", "min": 1, "max": 5, "sci": "PSQI*",
          "l": "Qualité globale de votre sommeil ?", "lo": "Très mauvaise", "hi": "Excellente"},
         {"id": "s_lat", "type": "choice", "sci": "PSQI · Jenkins*", "l": "Temps pour vous endormir ?",
          "o": [("l15", "< 15 min"), ("l1530", "15–30 min"), ("l3060", "30–60 min"), ("l60", "> 60 min")]},
         {"id": "s_rev", "type": "choice", "sci": "Jenkins*", "l": "Réveils nocturnes ou trop tôt sans vous rendormir ?",
          "o": [("r0", "Jamais / rare"), ("r1", "1×/sem"), ("r2", "2×/sem"), ("r3", "≥ 3×/sem")]},
     ]},
    {"id": "bienetre", "n": "03", "sec": "Corps ET tête",
     "title": "Ces 2 semaines, dans votre corps comme dans votre tête.",
     "intro": "Comment vous êtes-vous senti, physiquement et mentalement ?",
     "qs": [
         {"id": "b_humeur", "type": "scale", "min": 0, "max": 5, "sci": "WHO-5*",
          "l": "« Je me suis senti de bonne humeur, positif. »", "lo": "Jamais", "hi": "Tout le temps"},
         {"id": "b_calme", "type": "scale", "min": 0, "max": 5, "sci": "WHO-5*",
          "l": "« Je me suis senti calme et détendu. »", "lo": "Jamais", "hi": "Tout le temps"},
         {"id": "b_energie", "type": "scale", "min": 0, "max": 5, "sci": "WHO-5*",
          "l": "« Je me suis senti plein d'énergie. »", "lo": "Jamais", "hi": "Tout le temps"},
         {"id": "b_stress", "type": "scale", "min": 1, "max": 5, "sci": "PSS*",
          "l": "À quel point vous sentez-vous stressé, sous tension ?", "lo": "Pas du tout", "hi": "Énormément"},
         {"id": "b_pression", "type": "choice", "l": "Ressentez-vous de la pression (travail, compétition, vie perso) ?",
          "o": [("p_non", "Pas vraiment"), ("p_peu", "Un peu"), ("p_bcp", "Beaucoup")]},
         {"id": "b_social", "type": "choice", "sci": "lien social (OSSS)*",
          "l": "À quelle fréquence voyez-vous ou échangez-vous avec vos proches (amis, famille) ?",
          "o": [("soc0", "Rarement"), ("soc1", "Quelques fois par mois"), ("soc2", "Chaque semaine"), ("soc3", "Presque tous les jours")]},
         {"id": "b_exterieur", "type": "choice", "sci": "exposition nature*",
          "l": "Combien de temps passez-vous dehors, en plein air ou en nature, par semaine ?",
          "o": [("ext0", "Moins de 30 min"), ("ext1", "30 min – 1 h"), ("ext2", "1 – 2 h"), ("ext3", "2 h et +")]},
     ]},
    {"id": "recup", "n": "04", "sec": "Récupération", "title": "Votre récupération.",
     "intro": "Votre capacité à récupérer — d'une semaine chargée, du stress, du sport.",
     "qs": [
         {"id": "r_recup", "type": "scale", "min": 0, "max": 6, "sci": "SRSS*",
          "l": "En ce moment, vous sentez-vous reposé et rechargé ?", "lo": "Vidé", "hi": "Pleinement rechargé"},
         {"id": "r_tens", "type": "scale", "min": 0, "max": 6, "sci": "SRSS*",
          "l": "À quel point votre corps est-il tendu ou raide ?", "lo": "Détendu", "hi": "Très tendu"},
         {"id": "r_lourd", "type": "choice", "l": "Avez-vous les jambes lourdes ou une sensation de gonflement ?",
          "o": [("lo_j", "Jamais"), ("lo_p", "Parfois"), ("lo_s", "Souvent"), ("lo_ts", "Très souvent")]},
     ]},
    {"id": "douleur", "n": "05", "sec": "Douleur", "title": "Douleurs & tensions.",
     "intro": "Si vous en avez, précisons. Sinon, page vite passée.",
     "qs": [
         {"id": "d_zone", "type": "multi", "none": "none", "sci": "localisation",
          "l": "Douleurs ou tensions en ce moment ? Où ?", "hint": "Plusieurs choix possibles.",
          "o": [("none", "Aucune"), ("dos", "Dos / colonne"), ("artic", "Articulations"),
                ("muscle", "Muscles"), ("tendon", "Tendons"), ("autre", "Autres (viscéral, céphalées, gynéco…)")]},
         {"id": "d_int", "type": "scale", "min": 0, "max": 10, "cond": True, "sci": "EVA / NRS*",
          "l": "Intensité moyenne de la douleur ?", "lo": "0", "hi": "10"},
         {"id": "d_anc", "type": "choice", "cond": True, "sci": "IASP*", "l": "Depuis combien de temps ?",
          "o": [("a6", "< 6 semaines"), ("a63", "6 sem – 3 mois"), ("a3plus", "> 3 mois")]},
         {"id": "d_eval", "type": "choice", "cond": True, "l": "Déjà évaluée par un professionnel de santé ?",
          "o": [("oui", "Oui"), ("non", "Non")]},
         {"id": "d_cat", "type": "scale", "min": 0, "max": 4, "cond": True, "sci": "PCS*",
          "l": "« Quand j'ai mal, je pense que ça pourrait être grave ou ne jamais s'arrêter. »",
          "lo": "Pas du tout", "hi": "Tout le temps"},
         {"id": "d_verb", "type": "choice", "cond": True, "l": "Difficile de mettre des mots sur ce que vous ressentez ?",
          "o": [("v_non", "Non"), ("v_peu", "Un peu"), ("v_bcp", "Beaucoup")]},
     ]},
    {"id": "corps", "n": "06", "sec": "Corps & esprit", "title": "Le lien corps–esprit.",
     "intro": "Votre écoute de vous-même, et vos préférences.",
     "qs": [
         {"id": "i_notice", "type": "scale", "min": 0, "max": 5, "sci": "MAIA-2*",
          "l": "« Je remarque facilement les signaux de mon corps (fatigue, tension, faim). »",
          "lo": "Pas du tout", "hi": "Tout à fait"},
         {"id": "pref", "type": "choice", "l": "Vous êtes plutôt attiré par une approche…",
          "o": [("passive", "Passive, sensorielle et high-tech"), ("active", "Active (mouvement, mobilité, renfort)"),
                ("manuelle", "Manuelle (travail sur le corps)"), ("mentale", "Mentale (respiration, gestion du stress)"),
                ("sociale", "Sociale et conviviale (en groupe)")]},
     ]},
    {"id": "nutrition", "n": "07", "sec": "Nutrition", "title": "Votre alimentation.",
     "intro": "Quelques repères simples — sans rentrer dans les détails.",
     "qs": [
         {"id": "n_repas", "type": "choice", "l": "Combien de repas par jour en moyenne ?",
          "o": [("v1", "1"), ("v2", "2"), ("v3", "3"), ("v4", "4")]},
         {"id": "n_ultra", "type": "choice", "sci": "NOVA*",
          "l": "À quelle fréquence : aliments ultra-transformés, sodas, plats préparés ?",
          "o": [("u_rare", "Rarement"), ("u_parfois", "Parfois"), ("u_souvent", "Souvent"), ("u_tres", "Très souvent")]},
         {"id": "n_regime", "type": "choice", "l": "Votre type d'alimentation ?",
          "o": [("omni", "Pas de régime particulier"), ("flexi", "Flexitarien"), ("pesci", "Pescitarien"),
                ("vege", "Végétarien"), ("vegan", "Végan"), ("autre", "Autre")]},
         {"id": "n_fl", "type": "choice", "sci": "indice qualité*", "l": "Portions de fruits & légumes par jour ?",
          "o": [("fl0", "< 1"), ("fl1", "1–2"), ("fl2", "3–4"), ("fl3", "5 et +")]},
         {"id": "n_prot", "type": "choice", "l": "Une source de protéines à chaque repas principal ?",
          "o": [("p_rare", "Rarement"), ("p1", "1 repas"), ("p2", "2 repas"), ("p_almost", "Presque toujours")]},
         {"id": "n_hydra", "type": "choice", "l": "Combien d'eau buvez-vous par jour environ ?",
          "o": [("h1", "Moins d'1 L"), ("h2", "1 à 1,5 L"), ("h3", "1,5 à 2 L"), ("h4", "Plus de 2 L")]},
         {"id": "n_poisson", "type": "choice", "l": "Poisson gras / oméga-3 (saumon, sardines, noix, colza) ?",
          "o": [("pg0", "Jamais"), ("pg1", "< 1×/sem"), ("pg2", "1–2×/sem"), ("pg3", "2×/sem et +")]},
     ]},
]

AXES = ["sommeil", "forme", "recup", "stress", "confort", "nutrition"]
AXLBL = {"sommeil": "Sommeil", "forme": "Forme physique", "recup": "Récupération",
         "stress": "Stress", "confort": "Confort / douleurs", "nutrition": "Nutrition"}
RADLBL = ["Sommeil", "Forme", "Récup.", "Stress", "Confort", "Nutrition"]
LEVER = {"sommeil": "votre sommeil", "forme": "votre forme physique", "recup": "votre récupération",
         "stress": "votre gestion du stress", "confort": "votre gestion des douleurs", "nutrition": "votre alimentation"}
OBJ2AXIS = {"energie": "sommeil", "souffler": "stress", "douleur": "confort",
            "recup_sport": "recup", "force": "forme", "longevite": "forme", "rehab": "confort"}


def _tip(h, t, ref):
    return {"h": h, "t": t, "ref": ref}


ADVICE = {
    "sommeil": {"label": "Sommeil", "tips": [
        _tip("Régularité des horaires", "Misez sur la stabilité de vos heures de coucher et de lever plutôt que sur la durée : la régularité est un marqueur de santé et de longévité encore plus fort que le nombre d'heures.", "Windred et al., 2024"),
        _tip("Environnement propice", "Rendez votre chambre sombre, fraîche et calme, et baissez la lumière vive avant le coucher : une base clé d'une bonne hygiène de sommeil.", "Krizan & Hisler, 2022"),
        _tip("Déconnexion numérique", "Limitez les écrans le soir : chaque heure d'écran en plus est associée à un coucher retardé (~13 min) et à du sommeil perdu.", "He et al., 2025")]},
    "forme": {"label": "Forme physique", "tips": [
        _tip("La marche digestive", "Marchez 10 minutes après les repas pour réguler la glycémie et relancer la circulation, sans effort.", "Buffey et al., 2022"),
        _tip("Le renforcement bi-hebdomadaire", "Deux séances de renforcement par semaine, avec un peu d'aérobie quotidien, comptent parmi les meilleurs investissements santé (jusqu'à −40 % de mortalité).", "Sain et al., 2024"),
        _tip("La régularité avant l'intensité", "Commencez par deux séances réalistes de 15 min : la clé du succès, c'est la régularité du déclencheur, pas l'intensité.", "Milkman 2021 ; Islam 2022")]},
    "stress": {"label": "Stress", "tips": [
        _tip("Le soupir physiologique", "La technique la plus rapide pour faire chuter le stress : 3–4 cycles (double inspiration nasale puis longue expiration).", "Balban et al., 2023"),
        _tip("Les relations sociales", "Réinvestissez du temps dans vos liens sociaux : un effet protecteur sur la santé comparable à l'arrêt du tabac.", "Holt-Lunstad 2010 ; Inagaki 2021"),
        _tip("L'immersion thermique", "La douche alternée chaud/froid entraîne votre système nerveux à rester stable face au stress.", "Søberg et al., 2021")]},
    "confort": {"label": "Confort / douleurs", "tips": [
        _tip("Repenser l'alarme", "La douleur est un signal de protection, pas forcément une lésion : comprendre qu'« avoir mal ≠ être abîmé » diminue l'alarme et la peur de bouger.", "Louw et al., 2016"),
        _tip("Bouger progressivement", "N'attendez pas l'absence de douleur pour bouger : un mouvement guidé et progressif réduit les douleurs chroniques (jusqu'à −40 % pour la lombalgie).", "Kent et al., 2023"),
        _tip("Votre pharmacie naturelle", "Souffle (cohérence cardiaque), contrastes thermiques et massages activent vos circuits naturels de soulagement de la douleur.", "Tracey et al., 2020")]},
    "recup": {
        "sedentaire": {"label": "Récupération", "tips": [
            _tip("L'hydratation continue", "Buvez par petites gorgées pour 1,5–2 L/jour sans attendre la soif : cela soutient le métabolisme et dissipe la fatigue.", "Haller et al., 2022"),
            _tip("Marche digestive & coucher fixe", "10 min de marche après le déjeuner + une heure de coucher régulière, écrans coupés 30 min avant.", "Punna 2022 ; Windred 2024"),
            _tip("Loisir & lien social", "Après le travail, une activité de loisir partagée apaise l'esprit et restaure votre énergie.", "Arredondo, 2020")]},
        "mixte": {"label": "Récupération", "tips": [
            _tip("Mobilité & mouvement", "10–15 min de mobilité globale (thoracique, hanches, étirements fluides) améliore le lien corps-esprit et préserve l'énergie.", "Haller 2022 ; Erdoğan 2021"),
            _tip("Alternance thermique & souffle", "Douche contrastée (2–3 × 2 min chaud / 30 s froid) avec respiration apaisée : détente immédiate du corps et de l'esprit.", "Søberg, 2021"),
            _tip("Équilibre pro-perso", "Sanctuarisez 1–2 créneaux/semaine hors domicile et bureau pour bouger et récupérer.", "Mostert, 2009")]},
        "sportif": {"label": "Récupération", "tips": [
            _tip("Nutrition de récupération", "Soignez votre apport post-effort (protéines + glucides) pour réparer les fibres et recharger vos réserves.", "BJSM, 2018"),
            _tip("Régularité des horaires", "Stabilité des heures de coucher plutôt que durée : un marqueur de santé et de longévité.", "Windred et al., 2024"),
            _tip("Contraste thermique chaud/froid", "2–3 cycles (2 min chaud / 30 s froid) en contrôlant le souffle : récupération plus rapide, moins de courbatures.", "Haller 2022 ; Søberg 2021")]},
    },
    "nutrition": {
        "sedentaire": {"label": "Nutrition", "tips": [
            _tip("Protéines le matin", "Une vraie source de protéines au petit-déjeuner stabilise l'énergie sur la journée et protège vos muscles.", "J. Nutrition"),
            _tip("Reminéraliser l'eau", "La fatigue de l'après-midi vient souvent d'un manque d'eau minérale : visez une eau riche en magnésium plutôt qu'un 3e café.", ""),
            _tip("Bons lipides", "Les oméga-3 (noix, sardines, colza) freinent l'inflammation silencieuse responsable de la sensation de lourdeur.", "")]},
        "sportif": {"label": "Nutrition", "tips": [
            _tip("30 g de protéines post-effort", "Une dose complète d'acides aminés dans les 2 h après l'entraînement stimule le remodelage musculaire.", "BJSM, 2018"),
            _tip("Eau sodée à 150 %", "Après l'effort, compensez vos pertes avec du sodium pour recharger le volume sanguin.", "Sports Medicine"),
            _tip("Polyphénols ciblés", "Fruits rouges et baies, à distance de la séance, réduisent les courbatures et préservent votre force.", "BJSM, 2021")]},
        "vege": "Profil végétarien / végan : veillez à un apport en protéines suffisant et réparti (légumineuses + céréales, tofu, tempeh), et surveillez les carences fréquentes — fer, vitamine B12 (supplémentation recommandée), oméga-3, zinc et iode.",
    },
}

# =====================================================================
#  2. MOTEUR — pondération scientifique, red flags, persona, CRM
#     (A = dict des réponses {id_question: valeur} ; age = int)
# =====================================================================


def pain_active(A):
    z = A.get("d_zone") or []
    return len(z) > 0 and "none" not in z


def _get(d, key, default):
    v = d.get(key)
    return default if v is None else v


def compute_scores(A, age=35):
    """Retourne les 6 scores d'axe (0-100) selon la pondération V8."""
    age = age or 35
    ageF = max(0.88, 1 - max(0, age - 35) * 0.003)

    # --- Sommeil : PSQI + régularité MCTQ (régularité & qualité sur-pondérées, Windred 2024) ---
    regM = {"tres": 1, "plutot": .7, "assez": .35, "var": 0}.get(A.get("s_reg"), .5)
    qualM = (_get(A, "s_qual", 3) - 1) / 4
    latM = {"l15": 1, "l1530": .66, "l3060": .33, "l60": 0}.get(A.get("s_lat"), .5)
    durM = {"d8": .9, "d78": 1, "d67": .66, "d56": .33, "d5": 0}.get(A.get("s_duree"), .5)
    revM = {"r0": 1, "r1": .66, "r2": .33, "r3": 0}.get(A.get("s_rev"), .5)
    sommeil = ((1.25 * regM + 1.25 * qualM + latM + durM + revM) / 5.5) * 100

    # --- Forme physique : volume OMS 2020 + statut compétition + malus sédentarité (Ekelund 2016) + âge ---
    freqC = {"f0": 0, "f12": .45, "f34": .85, "f5": 1}.get(A.get("freq"), .4)
    competB = {"comp_reg": .10, "comp_occ": .05, "loisir": 0, "nonsport": 0}.get(A.get("compet"), 0)
    travailF = {"sed": .85, "mixte": 1, "phys": 1.08}.get(A.get("travail"), 1)
    forme = max(5, min(100, (freqC * travailF + competB) * 100 * ageF))

    # --- Récupération : SRSS (récup globale 0,7) + signe circulatoire (0,3) + âge ---
    recupC = _get(A, "r_recup", 3) / 6
    circC = {"lo_j": 1, "lo_p": .66, "lo_s": .33, "lo_ts": 0}.get(A.get("r_lourd"), .66)
    recup = max(4, (.7 * recupC + .3 * circC) * 100 * ageF)

    # --- Stress & moral : PSS + WHO-5 + lien social (Holt-Lunstad) + nature (White 2019) ---
    stressC = (5 - _get(A, "b_stress", 3)) / 4
    pressC = {"p_non": 1, "p_peu": .5, "p_bcp": 0}.get(A.get("b_pression"), .5)
    socialC = {"soc0": 0, "soc1": .4, "soc2": .75, "soc3": 1}.get(A.get("b_social"), .5)
    natureC = {"ext0": 0, "ext1": .4, "ext2": .75, "ext3": 1}.get(A.get("b_exterieur"), .5)
    stress = ((1.2 * stressC + 1 * _get(A, "b_humeur", 2.5) / 5 + 1 * _get(A, "b_calme", 2.5) / 5
               + 0.8 * pressC + 1 * socialC + 0.6 * natureC) / 5.6) * 100

    # --- Confort / douleurs : NRS (intensité ×2) + tensions ---
    tC = 1 - (_get(A, "r_tens", 3) / 6)
    if pain_active(A):
        confort = ((2 * (1 - min(1, _get(A, "d_int", 5) / 10)) + tC) / 3) * 100
    else:
        confort = tC * 100
    confort = max(6, confort)

    # --- Nutrition : indice qualité (fruits-légumes ×1,3) × malus NOVA multiplicatif ---
    fl = {"fl0": 0, "fl1": .4, "fl2": .75, "fl3": 1}.get(A.get("n_fl"), .5)
    prot = {"p_rare": 0, "p1": .4, "p2": .75, "p_almost": 1}.get(A.get("n_prot"), .5)
    hyd = {"h1": 0, "h2": .5, "h3": .9, "h4": 1}.get(A.get("n_hydra"), .5)
    poi = {"pg0": 0, "pg1": .35, "pg2": .85, "pg3": 1}.get(A.get("n_poisson"), .5)
    strc = {"v1": .4, "v2": .75, "v3": 1, "v4": .85}.get(A.get("n_repas"), .6)
    base = (1.3 * fl + prot + hyd + poi + strc) / 5.3
    malus = {"u_rare": 1, "u_parfois": .9, "u_souvent": .8, "u_tres": .6}.get(A.get("n_ultra"), .9)
    nutrition = max(4, base * malus * 100)

    return {"sommeil": sommeil, "forme": forme, "recup": recup,
            "stress": stress, "confort": confort, "nutrition": nutrition}


def global_score(scores):
    return round(sum(scores[k] for k in AXES) / len(AXES))


def palier(score):
    if score <= 20:
        return "Votre potentiel inexploité est immense : chaque petit ajustement vous apportera des bénéfices immédiats."
    if score <= 40:
        return "Les bases sont là, il ne reste qu'à structurer vos habitudes pour franchir un vrai cap d'énergie."
    if score <= 60:
        return "Un équilibre déjà solide : ciblez quelques leviers précis pour passer de la simple résistance à la pleine vitalité durable."
    if score <= 80:
        return "Excellente gestion de vos ressources : place aux réglages de précision pour maximiser votre forme."
    return "Maîtrise remarquable : votre récupération est optimale, vous pouvez concentrer votre énergie sur d'autres axes de performance."


def who5(A):
    return ((_get(A, "b_humeur", 2.5) + _get(A, "b_calme", 2.5) + _get(A, "b_energie", 2.5)) / 15) * 100


def red_flags(A):
    """Renvoie {'triggered':bool,'kind':str}. Un seul critère suffit -> conseiller."""
    pa = pain_active(A)
    sleep3 = (A.get("s_reg") in ("assez", "var")) and (A.get("s_duree") in ("d5", "d56")) and (_get(A, "s_qual", 3) <= 2)
    impt = pa and _get(A, "d_int", 0) > 7
    chron_no = pa and A.get("d_anc") == "a3plus" and A.get("d_eval") == "non"
    acute_no = pa and A.get("d_anc") in ("a6", "a63") and A.get("d_eval") == "non" and _get(A, "d_int", 0) > 5
    low_well = who5(A) <= 40
    triggered = sleep3 or impt or chron_no or acute_no or low_well
    if low_well:
        kind = "moral"
    elif impt or chron_no or acute_no:
        kind = "douleur"
    elif sleep3:
        kind = "sommeil"
    else:
        kind = "general"
    return {"triggered": triggered, "kind": kind}


RED_FLAG_WHY = {
    "moral": "Vos réponses sur votre moral et votre énergie sont basses : dans ce cas, un accompagnement humain est préférable à un protocole automatique.",
    "douleur": "Vous décrivez une douleur importante ou pas encore évaluée médicalement : par prudence, un avis humain doit précéder tout protocole.",
    "sommeil": "Votre sommeil paraît durablement perturbé sur plusieurs plans : mieux vaut en parler pour construire une réponse vraiment adaptée.",
    "general": "Certaines de vos réponses méritent un échange humain avant tout protocole.",
}


def profile_key(A):
    if A.get("compet") in ("comp_reg", "comp_occ") or A.get("freq") in ("f34", "f5"):
        return "sportif"
    if A.get("freq") == "f0" and A.get("travail") == "sed":
        return "sedentaire"
    if A.get("objectif") == "rehab" or A.get("phase") in ("reprise", "blesse"):
        return "sedentaire"
    return "mixte"


def get_advice(axis, A):
    if axis == "recup":
        return ADVICE["recup"][profile_key(A)]
    if axis == "nutrition":
        nk = "sportif" if profile_key(A) == "sportif" else "sedentaire"
        a = ADVICE["nutrition"][nk]
        vege = ADVICE["nutrition"]["vege"] if A.get("n_regime") in ("vege", "vegan") else None
        return {"label": a["label"], "tips": a["tips"], "vege": vege}
    return ADVICE[axis]


def restitution_axes(A, scores):
    """Axe 'demande' (priorité) + axe le plus faible (distinct)."""
    weak = sorted(AXES, key=lambda k: scores[k])[0]
    demande = OBJ2AXIS.get(A.get("objectif"), weak)
    second = weak
    if second == demande:
        second = next((k for k in sorted(AXES, key=lambda k: scores[k]) if k != demande), None)
    return demande, second


def persona(A, age, scores=None):
    if scores is None:
        scores = compute_scores(A, age)
    if A.get("compet") in ("comp_reg", "comp_occ"):
        qual = "Compétiteur"
    elif A.get("freq") in ("f5", "f34"):
        qual = "Sportif"
    elif A.get("freq") == "f12" or A.get("travail") == "phys":
        qual = "Actif"
    else:
        qual = "Sédentaire"
    senior = (age or 0) >= 60
    fit = scores["forme"]
    if A.get("phase") == "blesse" or A.get("objectif") == "rehab":
        adj = "blessé"
    elif A.get("objectif") in ("force", "recup_sport") and (A.get("compet") in ("comp_reg", "comp_occ") or fit >= 75):
        adj = "performeur"
    elif A.get("objectif") == "souffler" or _get(A, "b_stress", 0) >= 4:
        adj = "stressé"
    elif A.get("objectif") == "douleur" or pain_active(A):
        adj = "douloureux"
    elif A.get("objectif") == "energie":
        adj = "en quête d'énergie"
    elif A.get("objectif") == "longevite":
        adj = "en prévention"
    elif A.get("objectif") == "recup_sport":
        adj = "en récupération"
    else:
        adj = "en équilibre"
    label = ("Senior " if senior else "") + qual + " " + adj
    return {"label": label, "qualificatif": qual, "adjectif": adj, "senior": senior}


def besoins(A, scores):
    """Prestations candidates (coulisse CRM) à partir de la demande + 2 axes faibles."""
    m = {"sommeil": ["École du sommeil", "Sophrologie", "Neuromodulation"],
         "forme": ["Coaching", "Pilates", "Test physiologique"],
         "recup": ["Bain froid", "Sauna", "Contraste", "Photobiomodulation", "Pressothérapie"],
         "stress": ["Sophrologie", "Neuromodulation", "Massage sensoriel", "Préparation mentale"],
         "confort": ["Photobiomodulation", "Ostéopathie", "École de la douleur", "Mobilité"],
         "nutrition": ["Conseil nutrition"]}
    weak = sorted(AXES, key=lambda k: scores[k])[:2]
    out = []
    for ax in [OBJ2AXIS.get(A.get("objectif"), weak[0])] + weak:
        for s in m[ax]:
            if s not in out:
                out.append(s)
    if A.get("phase") == "blesse":
        for s in ["Photobiomodulation", "Contraste", "Préparation mentale (sportif blessé)"]:
            if s not in out:
                out.append(s)
    return out


def build_crm(A, contact):
    """Charge utile CRM — remplie TOUJOURS (le consentement recherche ne régit
    que la publication/exploitation scientifique des scores)."""
    age = contact.get("age")
    scores = compute_scores(A, age)
    g = global_score(scores)
    p = persona(A, age, scores)
    return {
        "prenom": contact.get("prenom"),
        "age": age,
        "metier": A.get("metier") or None,
        "activite": p["qualificatif"],
        "senior": p["senior"],
        "objectifPrioritaire": A.get("objectif"),
        "objectifsSecondaires": A.get("obj_sec") or [],
        "preference": A.get("pref"),
        "scores": scores,
        "scoreGlobal": g,
        "meilleurAxe": sorted(AXES, key=lambda k: -scores[k])[0],
        "axeFaible": sorted(AXES, key=lambda k: scores[k])[0],
        "persona": p["label"],
        "besoins": besoins(A, scores),
        "email": contact.get("email"),
        "newsletter": contact.get("newsletter", False),
        "consentementRecherche": contact.get("science", False),
    }


# =====================================================================
#  3. RADAR (matplotlib, noir & blanc) — optionnel
# =====================================================================

def radar_figure(scores, facecolor="#101010"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    vals = [scores[k] for k in AXES]
    N = len(vals)
    angles = [math.pi / 2 - i * 2 * math.pi / N for i in range(N)]  # départ en haut, sens horaire
    xs = [v / 100 * math.cos(a) for v, a in zip(vals, angles)]
    ys = [v / 100 * math.sin(a) for v, a in zip(vals, angles)]
    xs += xs[:1]
    ys += ys[:1]
    fig, ax = plt.subplots(figsize=(4.6, 4.6), subplot_kw=dict(aspect="equal"))
    fig.patch.set_facecolor(facecolor)
    ax.set_facecolor(facecolor)
    ax.axis("off")
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-1.35, 1.35)
    # grille
    for f in (0.25, 0.5, 0.75, 1.0):
        gx = [f * math.cos(a) for a in angles] + [f * math.cos(angles[0])]
        gy = [f * math.sin(a) for a in angles] + [f * math.sin(angles[0])]
        ax.plot(gx, gy, color="white", alpha=0.14, lw=1)
    for a in angles:
        ax.plot([0, math.cos(a)], [0, math.sin(a)], color="white", alpha=0.14, lw=1)
    # polygone data
    ax.fill(xs, ys, color="white", alpha=0.22)
    ax.plot(xs, ys, color="white", lw=2)
    for v, a in zip(vals, angles):
        px, py = v / 100 * math.cos(a), v / 100 * math.sin(a)
        ax.plot(px, py, "o", color="white", ms=5)
        ax.text(px, py + 0.09, f"{round(v)}%", color="white", ha="center", va="bottom", fontsize=9, fontweight="bold")
    for lbl, a in zip(RADLBL, angles):
        ax.text(1.18 * math.cos(a), 1.18 * math.sin(a), lbl, color="#CFCFCF",
                ha="center", va="center", fontsize=10)
    fig.tight_layout(pad=0.2)
    return fig


# =====================================================================
#  4. INTERFACE STREAMLIT
# =====================================================================

CSS = """
<style>
  .stApp { background:#101010; color:#F5F5F5; }
  h1,h2,h3,h4,p,label,span,div { color:#F5F5F5 !important; }
  .forge-mark { letter-spacing:.3em; font-weight:600; font-size:30px; text-align:center; }
  .forge-tag { color:#CFCFCF !important; text-align:center; letter-spacing:.04em; }
  .forge-sci { color:#9A9A9A !important; font-size:11px; font-style:italic; }
  .forge-score { font-size:54px; font-weight:300; text-align:center; }
  .forge-lbl { color:#9A9A9A !important; text-transform:uppercase; letter-spacing:.12em; font-size:12px; text-align:center; }
  .forge-valo { background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.2); border-radius:12px; padding:14px 16px; }
  .forge-flag { background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.3); border-radius:12px; padding:16px; }
  .forge-advice { border:1px solid rgba(255,255,255,.16); border-radius:12px; padding:14px 16px; margin-bottom:10px; }
  .stButton>button { background:#FFFFFF; color:#101010; border:none; border-radius:10px; font-weight:600; }
  .stButton>button:hover { background:#E6E6E6; color:#101010; }
</style>
"""


def _run_streamlit():
    import streamlit as st

    st.set_page_config(page_title="Forge — Capital récupération", page_icon="◼", layout="centered")
    st.markdown(CSS, unsafe_allow_html=True)
    ss = st.session_state
    ss.setdefault("step", 0)          # 0 = intro ; 1..len(PAGES) = pages ; +1 = contact ; +2 = résultats
    ss.setdefault("A", {})
    ss.setdefault("contact", {})

    n_intro, n_pages = 0, len(PAGES)
    step = ss.step
    A, contact = ss.A, ss.contact

    # ---------- INTRO ----------
    if step == n_intro:
        st.markdown('<div class="forge-mark">F O R G E</div>', unsafe_allow_html=True)
        st.markdown('<div class="forge-tag">De Corps et d\'Esprit</div>', unsafe_allow_html=True)
        st.markdown("### Forgez votre récupération.")
        st.write("En 6 minutes, découvrez votre **capital récupération** : vos points forts, "
                 "les ressources que vous n'exploitez pas encore, et des conseils issus de la science pour progresser.")
        c1, c2 = st.columns(2)
        contact["prenom"] = c1.text_input("Prénom", value=contact.get("prenom", ""))
        contact["age"] = c2.number_input("Âge", min_value=10, max_value=110,
                                         value=int(contact.get("age") or 30), step=1)
        if st.button("Commencer le bilan →"):
            if not contact["prenom"].strip():
                st.warning("Indiquez votre prénom pour commencer.")
            else:
                ss.step += 1
                st.rerun()
        return

    # ---------- PAGES DE QUESTIONS ----------
    if 1 <= step <= n_pages:
        pg = PAGES[step - 1]
        st.markdown(f'<div class="forge-lbl">{pg["n"]} · {pg["sec"]}</div>', unsafe_allow_html=True)
        st.markdown(f"### {pg['title'].replace('<b>','').replace('</b>','')}")
        st.caption(pg["intro"])

        for q in pg["qs"]:
            # question conditionnelle douleur
            if pg["id"] == "douleur" and q.get("cond") and not pain_active(A):
                continue
            label = q["l"] + (f'  ·  _{q["sci"]}_' if q.get("sci") else "")
            key = q["id"]
            if q["type"] == "text":
                A[key] = st.text_input(label, value=A.get(key, ""))
            elif q["type"] == "scale":
                default = A.get(key, (q["min"] + q["max"]) // 2)
                A[key] = st.slider(label, q["min"], q["max"], int(default),
                                   help=f'{q["lo"]} → {q["hi"]}')
                st.caption(f'{q["min"]} = {q["lo"]}  ·  {q["max"]} = {q["hi"]}')
            elif q["type"] == "multi":
                labels = [t for _, t in q["o"]]
                v2l = {v: t for v, t in q["o"]}
                l2v = {t: v for v, t in q["o"]}
                cur = [v2l[v] for v in A.get(key, []) if v in v2l]
                chosen = st.multiselect(label, labels, default=cur)
                vals = [l2v[t] for t in chosen]
                none_v = q.get("none")
                if none_v and v2l.get(none_v) in chosen and len(vals) > 1:
                    vals = [none_v]  # "Aucune" exclusif
                A[key] = vals
            else:  # choice
                labels = [t for _, t in q["o"]]
                v2l = {v: t for v, t in q["o"]}
                l2v = {t: v for v, t in q["o"]}
                cur = A.get(key)
                idx = labels.index(v2l[cur]) if cur in v2l else None
                chosen = st.radio(label, labels, index=idx, key=f"radio_{key}")
                A[key] = l2v.get(chosen)
            if q.get("sci"):
                st.markdown('<div class="forge-sci">* question adaptée d\'un questionnaire scientifique validé.</div>',
                            unsafe_allow_html=True)

        c1, c2 = st.columns([1, 1])
        if c1.button("← Retour"):
            ss.step -= 1
            st.rerun()
        if c2.button("Continuer →"):
            missing = [q["l"] for q in pg["qs"]
                       if not q.get("optional")
                       and not (pg["id"] == "douleur" and q.get("cond") and not pain_active(A))
                       and (A.get(q["id"]) in (None, "", []) and q["type"] != "scale")]
            if missing:
                st.warning("Merci de répondre à toutes les questions de la page.")
            else:
                ss.step += 1
                st.rerun()
        return

    # ---------- CONTACT ----------
    if step == n_pages + 1:
        st.markdown('<div class="forge-lbl">Presque fini</div>', unsafe_allow_html=True)
        st.markdown(f"### {contact.get('prenom','')}, découvre ton **capital récupération**.")
        contact["email"] = st.text_input("Email", value=contact.get("email", ""))
        contact["newsletter"] = st.checkbox("J'accepte de recevoir la newsletter Forge.",
                                            value=contact.get("newsletter", False))
        contact["science"] = st.checkbox("J'autorise l'utilisation anonymisée de mes réponses à des fins de publication scientifique.",
                                         value=contact.get("science", False))
        c1, c2 = st.columns(2)
        if c1.button("← Retour"):
            ss.step -= 1
            st.rerun()
        if c2.button("Voir mon bilan →"):
            import re
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", contact.get("email", "")):
                st.warning("Entre un email valide.")
            else:
                ss.crm = build_crm(A, contact)   # CRM rempli ici (brancher l'envoi réel)
                ss.step += 1
                st.rerun()
        return

    # ---------- RÉSULTATS ----------
    scores = compute_scores(A, contact.get("age"))
    g = global_score(scores)
    best = sorted(AXES, key=lambda k: -scores[k])[0]
    flag = red_flags(A)
    nom = contact.get("prenom", "")

    st.markdown('<div class="forge-lbl">Votre bilan</div>', unsafe_allow_html=True)
    st.markdown(f"#### {nom}, voici votre baromètre de récupération.")

    if flag["triggered"]:
        st.markdown(
            f'<div class="forge-flag"><b>On vous recommande d\'abord d\'échanger avec un conseiller.</b><br>'
            f'{RED_FLAG_WHY[flag["kind"]]} Un conseiller Forge fera le point avec vous et pourra, si nécessaire, '
            f'vous orienter vers un professionnel de santé (médecin…). Votre bilan complet reste affiché ci-dessous.</div>',
            unsafe_allow_html=True)
        st.button("Parler à un conseiller")

    st.markdown('<div class="forge-lbl" style="margin-top:14px">Votre capital récupération</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="forge-score">{g}%</div>', unsafe_allow_html=True)
    st.write(f"{nom}, vous mobilisez {g} % de votre capital récupération. {palier(g)}")

    st.pyplot(radar_figure(scores))

    st.markdown(f'<div class="forge-valo">Bravo, vous mobilisez déjà bien <b>{LEVER[best]}</b> comme levier. '
                "La science le montre : un seul changement ciblé suffit à améliorer tout l'équilibre. "
                "Concentrez votre énergie sur un axe à la fois — un pas après l'autre, pour des progrès durables.</div>",
                unsafe_allow_html=True)

    st.markdown("##### Vos conseils")
    demande, second = restitution_axes(A, scores)
    for axis, is_dem in [(demande, True), (second, False)]:
        if axis is None or (not is_dem and axis == demande):
            continue
        adv = get_advice(axis, A)
        head = "Répondre à votre priorité" if is_dem else "Votre prochain levier"
        html = f'<div class="forge-advice"><b>{head}</b> · <i>{AXLBL[axis]}</i><br><br>'
        for t in adv["tips"]:
            ref = f' <i>({t["ref"]})</i>' if t["ref"] else ""
            html += f'<b>{t["h"]}</b><br>{t["t"]}{ref}<br><br>'
        if adv.get("vege"):
            html += f'<i>{adv["vege"]}</i>'
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

    st.markdown('<div class="forge-advice" style="text-align:center">Chez Forge, on conçoit des programmes '
                'personnalisés pour progresser plus vite et ancrer vos résultats dans la durée.</div>',
                unsafe_allow_html=True)
    st.button("Rejoindre la communauté Forge")
    if st.button("↺ Refaire le bilan"):
        ss.step = 0
        ss.A = {}
        ss.contact = {}
        st.rerun()

    with st.expander("CRM / persona (coulisse — non affiché au client)"):
        st.json(ss.get("crm", build_crm(A, contact)))
    st.caption("Baromètre de bien-être fondé sur la littérature — ne remplace pas un avis médical.")


# =====================================================================
#  5. DÉMO CONSOLE (sans Streamlit)
# =====================================================================

def demo_cli():
    exemple = {
        "metier": "Comptable", "travail": "sed", "objectif": "energie", "obj_sec": ["souffler"],
        "compet": "nonsport", "freq": "f12", "phase": "na",
        "s_reg": "assez", "s_duree": "d56", "s_qual": 2, "s_lat": "l1530", "s_rev": "r1",
        "b_humeur": 3, "b_calme": 2, "b_energie": 2, "b_stress": 4, "b_pression": "p_bcp",
        "b_social": "soc1", "b_exterieur": "ext0",
        "r_recup": 2, "r_tens": 4, "r_lourd": "lo_p",
        "d_zone": ["none"], "i_notice": 2, "pref": "mentale",
        "n_repas": "v2", "n_ultra": "u_souvent", "n_regime": "omni",
        "n_fl": "fl1", "n_prot": "p1", "n_hydra": "h2", "n_poisson": "pg1",
    }
    contact = {"prenom": "Alex", "age": 42, "email": "alex@exemple.fr", "newsletter": True, "science": False}
    scores = compute_scores(exemple, contact["age"])
    g = global_score(scores)
    print("=" * 60)
    print(" FORGE — démo moteur (console)")
    print("=" * 60)
    print(f"Score global : {g}%  —  {palier(g)}")
    print("\nScores par axe :")
    for k in AXES:
        bar = "█" * int(scores[k] / 5)
        print(f"  {AXLBL[k]:<20} {round(scores[k]):>3}%  {bar}")
    rf = red_flags(exemple)
    print(f"\nRed flag : {rf['triggered']}  ({rf['kind']})")
    demande, second = restitution_axes(exemple, scores)
    print(f"Demande -> {AXLBL[demande]}   |   Prochain levier -> {AXLBL.get(second)}")
    print("\nCRM / persona :")
    import json
    print(json.dumps(build_crm(exemple, contact), ensure_ascii=False, indent=2))
    print("\n(Interface interactive : `pip install streamlit matplotlib` puis `streamlit run forge_questionnaire.py`)")


def _streamlit_context():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


if __name__ == "__main__":
    if _streamlit_context():
        _run_streamlit()
    else:
        demo_cli()
