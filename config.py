"""
Email Triage System Configuration.
"""

ACCOUNTS = [
    {
        "name": "test",
        "token_file": "token_test.json",
    }
]

OWNER = "name@company.com"
OWNER_SALES = OWNER   # TODO:  "sales@company.com"
OWNER_UCETNI = OWNER  # TODO: "accountant@company.com"

CATEGORIES = {
    "Obchod": {
        "popis": (
            "Poptávky a žádosti o cenovou nabídku, objednávky výroby (DPS/PCB, díly, "
            "plotr, výsek), žádosti o aktivaci objednávání z platformy " 
            "('New ordering activation request'), dotazy stávajících zákazníků k zakázce, "
            "ceně či termínu, a výrobní podklady/výkresy zaslané zákazníkem."
        ),
        "owner": OWNER_SALES,
        "sablona": (
            "Krátce potvrď, že poptávku/objednávku máme, a napiš, že připravíme nabídku "
            "a termín. Když jsou v mailu konkrétní parametry (počet ks, specifikace, "
            "číslo objednávky), krátce je zopakuj pro jistotu. Věcně, bez zbytečných frází. "
            "Ceny a termíny nevymýšlej – [doplnit]."
        ),
    },
    "Investori_Konference": {
        "popis": (
            "Dvě věci dohromady (obojí řeší CEO osobně): 1) INVESTOŘI – VC, andělé, "
            "fundraising, investiční kola, term sheet / SHA / ISA, žádosti o call ohledně "
            "investice; obchodní a founder konzultace či coaching (např. Saleshero). "
            "2) KONFERENCE A AKCE – pozvánky na konference, panely, přednášky, networking; "
            "a strategická partnerství či spolupráce mezi firmami."
        ),
        "owner": OWNER,
        "sablona": None,
    },
    "Fakturace": {
        "popis": (
            "Skutečné platby a doklady: přijaté faktury, účtenky a receipty, upomínky "
            "plateb, předplatná (obnovení, vypršení, změna tarifu), billing od nástrojů "
            "a dodavatelů. NEpatří sem obchodní konzultace ani nabídky – jen reálné "
            "faktury, platby a předplatná."
        ),
        "owner": OWNER_UCETNI,
        "sablona": None,
    },
    "Smlouvy_Urady": {
        "popis": (
            "Smlouvy, právní dokumenty k podpisu/revizi, datová schránka (datovka.gov.cz), "
            "úřady, oficiální a státní komunikace."
        ),
        "owner": OWNER,
        "sablona": None,
    },
    "Interni": {
        "popis": (
            "Interní e-maily od kolegů z Firma123 (doména @firma.cz) – "
            "provozní domluvy, interní schůzky a pozvánky, drobné dotazy uvnitř firmy, "
            "a sdílení interních dokumentů či složek (Google Drive) mezi kolegy."
        ),
        "owner": OWNER,
        "sablona": None,
    },
    "Sum": {
        "popis": (
            "Automatické notifikace nástrojů, onboarding a marketing SaaS služeb, nahrávky "
            "a shrnutí schůzek (Loom, Fathom, Atlassian), bezpečnostní a přihlašovací "
            "upozornění (nové přihlášení, passkey, důvěryhodné zařízení), ověřovací kódy, "
            "newslettery, reklama, cold outreach. Nevyžaduje pozornost člověka."
        ),
        "owner": None,
        "sablona": None,
    },
}

# --- Models (verified in docs.claude.com, July 2026) -------------------
MODEL_CLASSIFY = "claude-haiku-4-5"
MODEL_DRAFT = "claude-sonnet-5"


LOOKBACK_DAYS = 2
MAX_PER_ACCOUNT = 20
LABEL_PREFIX = "Triage/"
PROCESSED_LABEL = "Triage/Roztrizeno"

ARCHIVE_CATEGORIES = []

DIGEST_MODE = "draft"