"""
Felsefi Araştırma Sistemi — Flask sunucusu
Kullanım: python server.py

Pipeline (objektiflik odaklı, 6 aşama):
  0. Pozisyon Haritalayıcı — sorudaki en güçlü iki karşıt pozisyonu belirler (JSON, akışsız)
  1. Savunucu A ─┐  paralel: her biri bir pozisyonun EN GÜÇLÜ halini (steelman) savunur
  2. Savunucu B ─┘
  3. Kör Eleştirmen — raporları çerçeve adlarını BİLMEDEN denetler + JSON objektiflik rubriği üretir
  4. Sentezci — seçilen sentez çerçevesiyle bütünleştirir
  5. Çürütücü — sentezi çürütmeye çalışır (devil's advocate)
  6. Nihai Sentez — çürütme ışığında revize edilmiş son yanıt
"""
import os
from pathlib import Path

# .env dosyasını yükle (python-dotenv varsa)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from flask import Flask, request, Response, send_from_directory, jsonify
import json
import queue
import re
import threading
import warnings
warnings.filterwarnings("ignore")

app = Flask(__name__, static_folder=".")

MODEL = "claude-sonnet-4-6"
TEMPERATURE = 0.3          # tekrarlanabilirlik: aynı soru ≈ aynı analiz


# ── Statik dosyalar ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# ── Framework prompt kataloğu ─────────────────────────────────────────────────

FRAMEWORKS = {
    # ARAŞTIRMA
    "analytic": {
        "name": "Analitik Felsefe",
        "thinkers": "Russell, Frege, Wittgenstein",
        "role_suffix": "Analitik Felsefe yöntemiyle çalışan",
        "instruction": (
            "Analitik Felsefe yöntemiyle araştır:\n"
            "• Merkezi kavramları sıkı şekilde tanımla; belirsiz terimleri netleştir\n"
            "• Argümanları önerme biçiminde yeniden yaz ve mantıksal geçerliliklerini test et\n"
            "• Dil oyunlarını ve kullanım bağlamlarını incele (geç Wittgenstein)\n"
            "• Her iddiayı yanlışlanabilirlik testine tabi tut\n"
            "• Kavramsal ayrımları netleştir; muğlak kullanımları ifşa et\n"
            "• 'Bu sözcük burada tam olarak ne anlama geliyor?' sorusunu merkeze al"
        ),
    },
    "phenomenology": {
        "name": "Fenomenoloji",
        "thinkers": "Husserl, Heidegger, Merleau-Ponty",
        "role_suffix": "Fenomenolojik yöntemle çalışan",
        "instruction": (
            "Fenomenolojik yöntemle araştır:\n"
            "• Epoché uygula: doğal tutumu ve ön yargıları paranteze al\n"
            "• Eidetik redüksiyon: değişmez özsel yapıları (eidos) ortaya çıkar\n"
            "• Birinci tekil şahıs perspektifini ve yaşanmış deneyimi merkeze al\n"
            "• Zaman-içinde-varlık (Dasein), atılmışlık ve kaygı kavramlarını değerlendir\n"
            "• Bedensel varoluş ve algının bilişsel temelini incele (Merleau-Ponty)\n"
            "• 'Bu deneyim bilinçte nasıl açılıyor?' sorusunu merkeze al"
        ),
    },
    "pragmatism": {
        "name": "Pragmatizm",
        "thinkers": "Dewey, James, Peirce",
        "role_suffix": "Pragmatist yöntemle çalışan",
        "instruction": (
            "Pragmatist yöntemle araştır:\n"
            "• Her kavramı pratik sonuçları üzerinden değerlendir (Peirce'in pragmatik maksimi)\n"
            "• 'Bu inancı benimsemek hayatımızı nasıl değiştirir?' sorusunu sor\n"
            "• Deneysel doğrulama: iddialar pratikte ne tür somut farklar yaratıyor?\n"
            "• Hakikati statik değil, işe yarayan bir süreç olarak ele al (James)\n"
            "• Dewey'in araçsalcılığı: düşünce bir problem-çözme aracıdır\n"
            "• Demokratik pratik ve toplumsal katılımın bilgi üretimdeki rolünü sorgula"
        ),
    },
    "critical_theory": {
        "name": "Eleştirel Teori",
        "thinkers": "Habermas, Adorno, Horkheimer",
        "role_suffix": "Frankfurt Okulu Eleştirel Teorisi çerçevesinde çalışan",
        "instruction": (
            "Eleştirel Teori çerçevesiyle araştır:\n"
            "• İdeolojiyi ifşa et: hangi çıkarlar 'evrensel gerçek' maskesi takıyor?\n"
            "• Araçsal akıl eleştirisi: bu düşünce sistemi hangi iktidar yapısını meşrulaştırıyor?\n"
            "• İletişimsel eylem (Habermas): ideal konuşma durumundan sapmaları tespit et\n"
            "• Kültür endüstrisi: bu fikir nasıl yeniden üretiliyor ve kim için?\n"
            "• Özgürleşim potansiyeli: bu analiz kimin özgürleşimine katkı sağlar?\n"
            "• Aydınlanmanın diyalektiği: ilerleme söylemi ne üretiyor, ne bastırıyor?"
        ),
    },
    "genealogy": {
        "name": "Soykütük Yöntemi",
        "thinkers": "Foucault, Nietzsche",
        "role_suffix": "Soykütük yöntemiyle çalışan",
        "instruction": (
            "Soykütük yöntemiyle araştır:\n"
            "• Kavramların tarihsel oluşumunu ve süreksizliklerini izle\n"
            "• Güç-bilgi ilişkilerini harita çıkar: bu 'hakikat' kimin gücünü pekiştiriyor?\n"
            "• Ahlaki değerlerin kökenini güç ilişkilerine götür (Nietzsche'nin değer eleştirisi)\n"
            "• Episteme dönüşümlerini tespit et: hangi düşünce rejimi hangi bilgiyi mümkün kılıyor?\n"
            "• Normalleştirme ve dışlama mekanizmalarını analiz et\n"
            "• 'Bu kavram her zaman böyle miydi ve kim böyle yaptı?' sorusunu merkeze al"
        ),
    },
    "dialectic": {
        "name": "Diyalektik Yöntem",
        "thinkers": "Hegel",
        "role_suffix": "Hegelci diyalektik yöntemle çalışan",
        "instruction": (
            "Hegelci diyalektik yöntemle araştır:\n"
            "• Tez: konunun en güçlü ilk formülasyonunu kur\n"
            "• Antitez: bu tezin kendi içindeki çelişkiyi ve zorunlu olumsuzlamasını bul\n"
            "• Aufhebung (aşma): tez ve antitezi daha yüksek bir birlik içinde hem kaldır hem koru\n"
            "• Her kavramı kendi karşıtıyla olan ilişkisi içinde analiz et\n"
            "• Tarihin diyalektik hareketi: bu fikir hangi tarihsel çelişkiden doğdu?\n"
            "• Somut-evrensel: soyut geneli somut tikel örneklerle diyalektize et"
        ),
    },
    # ELEŞTİRİ
    "impartial_spectator": {
        "name": "Tarafsız Gözlemci",
        "thinkers": "Adam Smith",
        "role_suffix": "Adam Smith'in Tarafsız Gözlemci yöntemiyle çalışan",
        "instruction": (
            "Adam Smith'in Tarafsız Gözlemci yöntemiyle eleştir:\n"
            "• Hiçbir tarafın bakış açısını önceden benimseme; eşit mesafeyi koru\n"
            "• Her argümanın nasıl değil, neden öyle sunulduğunu sor\n"
            "• Sempati kapasitesiyle tüm pozisyonları anla; ama çıkar körlüğünün ötesinde dur\n"
            "• Retorik ağırlık mekanizmalarını tespit et: hangi argümanlar orantısız yer kapladı?\n"
            "• Araştırmacının kör noktalarını ve epistemik konumunu sistematik olarak ortaya koy\n"
            "• 'Bu analiz soruyu mu yanıtlıyor, yoksa sorunun ne olmasını istiyoruz mu?' diye sor"
        ),
    },
    "cognitive_bias": {
        "name": "Bilişsel Önyargı Analizi",
        "thinkers": "Kahneman, Tversky",
        "role_suffix": "Kahneman-Tversky bilişsel önyargı kataloğuyla çalışan",
        "instruction": (
            "Kahneman-Tversky bilişsel önyargı çerçevesiyle eleştir:\n"
            "• Sistem 1 (sezgisel, hızlı) ile Sistem 2 (analitik, yavaş) ayrımını uygula\n"
            "• Teyit önyargısı: araştırmacı mevcut inançlarını doğrulayan kanıtlara mı yöneldi?\n"
            "• Tutarlılık yanılsaması: gerçekte belirsiz şeyler tutarlı mı sunuldu?\n"
            "• Temsil buluşsalı: kullanılan örnekler istatistiksel olarak temsili mi?\n"
            "• Çerçeveleme etkisi: farklı çerçeveleme farklı sonuçlar doğurur muydu?\n"
            "• Müsait olma buluşsalı: kolayca akla gelen örnekler aşırı ağırlık taşıyor mu?\n"
            "• Bilgi yanılsaması: araştırmacı ne kadar bildiğini abartıyor mu?"
        ),
    },
    "research_programs": {
        "name": "Araştırma Programları",
        "thinkers": "Lakatos",
        "role_suffix": "Lakatos'un Araştırma Programları metodolojisiyle çalışan",
        "instruction": (
            "Lakatos'un Araştırma Programları metodolojisiyle eleştir:\n"
            "• Sert çekirdek: araştırmacının vazgeçmediği dokunulmaz temel varsayımlar neler?\n"
            "• Koruyucu kuşak: çekirdeği korumak için hangi yardımcı hipotezler devreye giriyor?\n"
            "• Pozitif sezgisel: araştırma programı nasıl genişliyor, nereye yönlendirilmiş?\n"
            "• Negatif sezgisel: hangi sorular metodolojik olarak önceden dışlanmış?\n"
            "• Program ilerleyici mi (yeniolgular öngörüyor mu) yoksa gerilemeye mi girmiş?\n"
            "• Araştırmacı kendi programını haklılaştırmak için anakronistik yeniden inşa yapıyor mu?"
        ),
    },
    "paradigm": {
        "name": "Paradigma Analizi",
        "thinkers": "Kuhn",
        "role_suffix": "Kuhn'un paradigma çerçevesiyle çalışan",
        "instruction": (
            "Kuhn'un paradigma analiziyle eleştir:\n"
            "• Araştırma hangi paradigma içinde yürütülüyor? Görünmez varsayımları neler?\n"
            "• Normal bilim mi, anomali mi, kriz mi, devrim mi? Araştırmacı hangi aşamada?\n"
            "• Paradigmalar arası ölçülemezlik: farklı çerçeveler gerçekten karşılaştırılabilir mi?\n"
            "• Araştırmacı anormallileri paradigmaya uydurmak için 'bulmaca çözüyor' mu?\n"
            "• Eğitimle içselleştirilen görünmez normatif boyut nerede devrede?\n"
            "• Bu araştırma hangi paradigmayı sarsıyor, hangisini pekiştiriyor?"
        ),
    },
    "epistemic_anarchy": {
        "name": "Epistemik Anarşizm",
        "thinkers": "Feyerabend",
        "role_suffix": "Feyerabend'in epistemik anarşizmiyle çalışan",
        "instruction": (
            "Feyerabend'in epistemik anarşizmiyle eleştir:\n"
            "• 'Her şey gider' (anything goes): araştırmacı hangi metodolojik kuralı mutlaklaştırıyor?\n"
            "• Bilimin özel statüsü: bu ayrıcalık nasıl meşrulaştırılıyor ve sorgulanıyor mu?\n"
            "• Karşı-tümevarım: mevcut teoriye aykırı veriler sistematik olarak görmezden geliniyor mu?\n"
            "• Çoğulculuk ilkesi: rakip teoriler gerçekten eşit fırsatla değerlendirildi mi?\n"
            "• Bilim-dışı bilgi gelenekleri (mitoloji, geleneksel bilgelik) dışlandı mı?\n"
            "• Metodolojik monotonizme karşı: tek doğru yöntem yoktur — araştırma bunu yansıtıyor mu?"
        ),
    },
    # SENTEZ
    "aqal": {
        "name": "AQAL / Dört Kadran",
        "thinkers": "Ken Wilber",
        "role_suffix": "Wilber'ın AQAL modeliyle çalışan",
        "instruction": (
            "Wilber'ın AQAL (All Quadrants All Levels) modeliyle sentezle:\n"
            "• ÜST-SOL (Ben/İç-Bireysel): fenomenoloji, bilinç, öznel deneyim boyutu\n"
            "• ÜST-SAĞ (O/Dış-Bireysel): nörobiyoloji, davranış, nesnel süreçler boyutu\n"
            "• ALT-SOL (Biz/İç-Kolektif): kültür, anlam, paylaşılan değerler boyutu\n"
            "• ALT-SAĞ (Onlar/Dış-Kolektif): kurumlar, ekonomi, güç yapıları boyutu\n"
            "• Pre/Trans Fallacy: ön-rasyonel ile trans-rasyoneli karıştırma hatasını tespit et\n"
            "• Flatland: hangi kadranlara indirgeme yapılmış, hangisi ihmal edilmiş?\n"
            "• Gerçek entegrasyon: sahte uzlaşıyı gerilimi koruyan bütünleşmeden ayır"
        ),
    },
    "dialectic_synth": {
        "name": "Diyalektik Sentez",
        "thinkers": "Hegel, Marx",
        "role_suffix": "Hegelci-Marksist diyalektik sentezle çalışan",
        "instruction": (
            "Hegelci-Marksist diyalektik sentezle bütünleştir:\n"
            "• Araştırma ve eleştiri raporlarındaki temel çelişkileri (Widerspruch) tespit et\n"
            "• Her çelişkiyi Aufhebung ile aş: hem kaldır hem koru hem yükselt\n"
            "• Tarihsel maddecilik: bu fikirler hangi maddi ve sınıfsal koşullardan doğuyor?\n"
            "• Somut-evrensel: soyut birliği somut tikellerle diyalektize et\n"
            "• Yabancılaşma: araştırmanın hangi boyutu özne-nesne ayrışmasını yeniden üretiyor?\n"
            "• Tarihsel zorunluluk: bu tartışma hangi daha geniş tarihsel hareketi temsil ediyor?"
        ),
    },
    "reflective_eq": {
        "name": "Düşünümsel Denge",
        "thinkers": "Rawls",
        "role_suffix": "Rawls'un düşünümsel denge yöntemiyle çalışan",
        "instruction": (
            "Rawls'un düşünümsel denge yöntemiyle sentezle:\n"
            "• Güçlü sezgiler: araştırmadan hangi sezgisel yargılar çıkıyor? Bunlar başlangıç noktası\n"
            "• İlkeler: bu sezgileri en tutarlı biçimde açıklayan ilkeler neler?\n"
            "• Dar denge: sezgi-ilke uyumsuzluklarını gider; gerekirse sezgileri revize et\n"
            "• Geniş denge: arka plan teorileri dahil edilerek daha kapsamlı tutarlılık ara\n"
            "• Döngüsel süreç: ilke → sezgi → revizyon → yeni ilke döngüsünü işlet\n"
            "• Özgün konum: 'cehalet peçesi' arkasındaki taraflar hangi ilkeleri seçer?"
        ),
    },
    "participatory": {
        "name": "Katılımcı Epistemoloji",
        "thinkers": "Ferrer",
        "role_suffix": "Ferrer'in katılımcı epistemolojisiyle çalışan",
        "instruction": (
            "Ferrer'in katılımcı epistemoloji çerçevesiyle sentezle:\n"
            "• Bilgi tekil öznenin keşfi değil, ilişkisel ve katılımcı bir ortak üretimdir\n"
            "• Çoğul ontoloji: birden fazla gerçeklik katmanı olabilir; hiyerarşik olmayan çoğulculuk\n"
            "• Gelenekler arası diyalog: farklı spiritüel ve felsefi gelenekler ortak anlam üretebilir\n"
            "• Bedensel, duygusal ve zihinsel bilme biçimlerini bütünleştir\n"
            "• Enaktif biliş: bilen özne ve bilinen nesne birbirini yaratır\n"
            "• 'Bu sentez kimin katılımını dışlıyor?' sorusunu merkeze al"
        ),
    },
}

DEFAULT_FRAMEWORKS = {
    "research": "analytic",
    "critique": "impartial_spectator",
    "synthesis": "aqal",
}

# Atıf disiplini — tüm araştırmacı ve sentezci ajanlarına eklenir
CITATION_RULES = (
    "ATIF KURALLARI:\n"
    "• Her önemli iddiayı düşünür + eser referansıyla destekle "
    "(ör. Wigner 1960, 'The Unreasonable Effectiveness of Mathematics...').\n"
    "• Emin olmadığın atıf UYDURMA. Kaynağından emin değilsen 'yaygın yorumlardan biri' de "
    "ve atıf verme.\n"
    "• İkincil aktarım kullandıysan bunu belirt."
)


# ── Pipeline aşamaları ───────────────────────────────────────────────────────
# Sabit yapı: 0-1 savunucular (paralel), 2 kör eleştirmen, 3 sentez,
#             4 çürütücü, 5 nihai sentez

def _stage_defs(rfw, cfw, sfw, positions):
    """UI'ya gönderilecek aşama başlıkları."""
    return [
        {"title": "Savunucu A", "subtitle": positions[0]["label"], "color": "cyan"},
        {"title": "Savunucu B", "subtitle": positions[1]["label"], "color": "cyan"},
        {"title": "Kör Eleştirmen", "subtitle": cfw["name"], "color": "violet"},
        {"title": "Sentezci", "subtitle": sfw["name"], "color": "gold"},
        {"title": "Çürütücü", "subtitle": "Devil's Advocate", "color": "red"},
        {"title": "Nihai Sentez", "subtitle": sfw["name"] + " — revize", "color": "gold"},
    ]


def _map_positions(client, question: str) -> list[dict]:
    """Sorudaki en güçlü iki karşıt pozisyonu belirler (akışsız, hızlı)."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        temperature=0.0,
        system=(
            "Felsefi bir sorudaki en güçlü iki KARŞIT pozisyonu belirlersin. "
            "Yalnızca geçerli JSON döndürürsün, başka hiçbir şey yazmazsın."
        ),
        messages=[{
            "role": "user",
            "content": (
                f'Soru: "{question}"\n\n'
                "Bu soruya verilebilecek en güçlü iki karşıt pozisyonu belirle. "
                "Pozisyonlar gerçekten karşıt olmalı ve alandaki ana tartışma hattını yansıtmalı.\n\n"
                'Şu formatta yanıtla: {"positions": [{"label": "<3-6 kelimelik pozisyon adı>", '
                '"claim": "<pozisyonun tek cümlelik temel iddiası>"}, {...}]}'
            ),
        }],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    data = json.loads(match.group(0))
    positions = data["positions"][:2]
    if len(positions) < 2:
        raise ValueError("Pozisyon haritalayıcı iki pozisyon döndüremedi")
    return positions


def _advocate_prompts(question: str, rfw: dict, position: dict, other: dict):
    """Bir pozisyonun steelman savunusu için (system, user) çifti."""
    system = (
        f"Sen {rfw['name']} geleneğini ({rfw['thinkers']}) derinlemesine bilen ve bunu "
        "birincil araştırma yöntemi olarak kullanan bir filozofsun. "
        "Görevin sana verilen pozisyonun EN GÜÇLÜ savunusunu (steelman) kurmak — "
        "karikatürünü değil, en zeki savunucusunun yapacağı savunmayı. "
        "Konuyla ilgili olduğu ölçüde farklı kültür ve geleneklerden düşünürleri de kapsarsın. "
        "Türkçe yazarsın, markdown başlıkları ve **kalın** vurgular kullanabilirsin."
    )
    user = (
        f'Soru: "{question}"\n\n'
        f"SAVUNACAĞIN POZİSYON: {position['label']}\n"
        f"Temel iddia: {position['claim']}\n\n"
        f"KARŞIT POZİSYON (savunma, ama ciddiye al): {other['label']} — {other['claim']}\n\n"
        f"=== KULLANILACAK ARAŞTIRMA ÇERÇEVESİ: {rfw['name'].upper()} ({rfw['thinkers']}) ===\n"
        f"{rfw['instruction']}\n\n"
        f"{CITATION_RULES}\n\n"
        "=== GÖREV ===\n"
        "1. Pozisyonun en güçlü 3-4 argümanını kur; her birini atıflarla destekle\n"
        "2. Karşıt pozisyonun EN GÜÇLÜ itirazını dürüstçe aktar ve yanıtla\n"
        "3. Pozisyonun tarihsel ve kültürlerarası savunucularını göster\n"
        "4. Pozisyonun kendi içindeki en zayıf noktayı açıkça kabul et (tek paragraf)\n\n"
        "En az 600 kelimelik, bölümlere ayrılmış bir savunma raporu yaz."
    )
    return system, user


def _critic_prompts(question: str, cfw: dict, output_a: str, output_b: str,
                    positions: list[dict]):
    """Kör eleştiri: eleştirmen hangi araştırma çerçevesinin kullanıldığını BİLMEZ."""
    system = (
        f"Sen {cfw['name']} metodolojisini ({cfw['thinkers']}) ustalıkla uygulayan "
        "bir epistemik hakemsin. Hiçbir tarafın bakış açısını önceden benimsemeden "
        "tüm argümanları eşit mesafeden değerlendirirsin. "
        "Raporların hangi yöntemle yazıldığı sana bilinçli olarak söylenmedi; "
        "yalnızca metnin kendisini denetlersin. "
        "Türkçe yazarsın, markdown başlıkları ve **kalın** vurgular kullanabilirsin."
    )
    user = (
        f'Soru: "{question}"\n\n'
        "Aşağıda iki karşıt pozisyonun savunma raporları var. Görevin iki raporu "
        "epistemik açıdan denetlemek ve KARŞILAŞTIRMALI bir objektiflik analizi yapmak.\n\n"
        f"=== KULLANILACAK ELEŞTİRİ ÇERÇEVESİ: {cfw['name'].upper()} ({cfw['thinkers']}) ===\n"
        f"{cfw['instruction']}\n\n"
        "=== ELEŞTİRİ EKSENLERİ ===\n"
        "1. Her raporun en güçlü ve en zayıf argümanı\n"
        "2. Simetri denetimi: iki pozisyon eşit ciddiyette mi savunulmuş?\n"
        "3. Retorik ağırlık: hangi rapor hangi mekanizmalarla ikna etmeye çalışıyor?\n"
        "4. Atıf denetimi: şüpheli, doğrulanamaz veya bağlamından koparılmış görünen atıflar\n"
        "5. Her iki raporun ortak kör noktası: ikisinin de sormadığı soru ne?\n\n"
        "En az 500 kelimelik epistemik denetim raporu yaz.\n\n"
        f"=== RAPOR A — Pozisyon: {positions[0]['label']} ===\n{output_a}\n\n"
        f"=== RAPOR B — Pozisyon: {positions[1]['label']} ===\n{output_b}"
    )
    return system, user


_RUBRIC_TOOL = {
    "name": "submit_rubric",
    "description": "Objektiflik rubriğini yapılandırılmış olarak gönder.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reports": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": ["A", "B"]},
                        "strongest_argument": {"type": "string"},
                        "steelman_quality": {"type": "integer", "minimum": 1, "maximum": 5},
                        "citation_reliability": {"type": "integer", "minimum": 1, "maximum": 5},
                        "rhetorical_load": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "required": ["id", "strongest_argument", "steelman_quality",
                                 "citation_reliability", "rhetorical_load"],
                },
            },
            "symmetry_score": {"type": "integer", "minimum": 1, "maximum": 5},
            "suspect_citations": {"type": "array", "items": {"type": "string"}},
            "shared_blind_spot": {"type": "string"},
            "overall_objectivity": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["reports", "symmetry_score", "suspect_citations",
                     "shared_blind_spot", "overall_objectivity"],
    },
}


def _rubric_call(client, question: str, output_a: str, output_b: str,
                 critique: str, positions: list[dict]):
    """Objektiflik rubriği — zorunlu tool call ile garantili-geçerli JSON."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        temperature=0.0,
        system=(
            "Sen epistemik denetim sonuçlarını sayısal rubriğe çeviren bir hakemsin. "
            "Puanlarını denetim raporundaki bulgulara dayandırırsın."
        ),
        tools=[_RUBRIC_TOOL],
        tool_choice={"type": "tool", "name": "submit_rubric"},
        messages=[{
            "role": "user",
            "content": (
                f'Soru: "{question}"\n\n'
                f"İki karşıt savunma raporu (A: {positions[0]['label']}, "
                f"B: {positions[1]['label']}) ve epistemik denetim raporu aşağıda. "
                "Bunlara dayanarak rubriği doldur. rhetorical_load için düşük puan iyidir; "
                "symmetry_score iki pozisyonun eşit ciddiyette savunulup savunulmadığını, "
                "overall_objectivity sürecin bütününü puanlar. suspect_citations yalnızca "
                "denetimde şüpheli bulunan atıfları içerir (yoksa boş liste).\n\n"
                f"=== RAPOR A ===\n{output_a}\n\n"
                f"=== RAPOR B ===\n{output_b}\n\n"
                f"=== EPİSTEMİK DENETİM ===\n{critique}"
            ),
        }],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise ValueError("Rubrik tool çağrısı dönmedi")


def _synth_prompts(question: str, sfw: dict, output_a: str, output_b: str,
                   critique: str, positions: list[dict]):
    system = (
        f"Sen {sfw['name']} modelini ({sfw['thinkers']}) derinlemesine bilen "
        "bir entegral filozofsun. Gerçekliğin birbirine indirgenemeyen boyutlarını "
        "bütünleştirmeyi görev sayarsın; hiçbir tekil bakış açısının tek başına "
        "yeterli olmadığını bilirsin. Sahte uzlaşı üretmezsin: gerilimleri koruyan "
        "dürüst bir entegrasyon hedeflersin. "
        "Türkçe yazarsın, markdown başlıkları ve **kalın** vurgular kullanabilirsin."
    )
    user = (
        f'"{question}" sorusu bağlamında, iki karşıt savunma raporunu ve epistemik '
        "denetim raporunu sentezle.\n\n"
        f"=== KULLANILACAK SENTEZ ÇERÇEVESİ: {sfw['name'].upper()} ({sfw['thinkers']}) ===\n"
        f"{sfw['instruction']}\n\n"
        f"{CITATION_RULES}\n\n"
        "=== SENTEZ GÖREVİ ===\n"
        "1. İki pozisyon arasındaki gerçek gerilim noktalarını belirle\n"
        "2. Eleştirmenin tespit ettiği bias ve kör noktaları sentezde düzelt\n"
        "3. Seçilen sentez çerçevesiyle iki pozisyonu bütünleştir — hangisi hangi "
        "boyutta haklı?\n"
        "4. Sahte uzlaşıdan kaçın: çözülemeyen gerilimleri açıkça çözülmemiş olarak bırak\n"
        "5. Kapanış: bu soruyu sormaya devam etmenin önemi\n\n"
        "En az 600 kelimelik entegral sentez raporu yaz.\n\n"
        f"=== RAPOR A — {positions[0]['label']} ===\n{output_a}\n\n"
        f"=== RAPOR B — {positions[1]['label']} ===\n{output_b}\n\n"
        f"=== EPİSTEMİK DENETİM ===\n{critique}"
    )
    return system, user


def _refuter_prompts(question: str, synthesis: str):
    system = (
        "Sen görevi verilen metni ÇÜRÜTMEK olan bir felsefi hasımsın (devil's advocate). "
        "Nazik olmak zorunda değilsin ama dürüst olmak zorundasın: gerçek zayıflıkları "
        "bul, olmayan zayıflık uydurma. Türkçe yazarsın, markdown kullanabilirsin."
    )
    user = (
        f'Soru: "{question}"\n\n'
        "Aşağıdaki sentez raporunu çürütmeye çalış:\n"
        "1. Sentezin en zayıf üç noktası — mantıksal boşluk, kanıtsız sıçrama veya "
        "sahte uzlaşı\n"
        "2. Sentezin görmezden geldiği en güçlü karşı-argüman\n"
        "3. Sentez çerçevesinin kendisinin bu soruya dayattığı çarpıtma\n"
        "4. Eğer sentez savunulabilir durumdaysa, bunu da dürüstçe söyle — "
        "hangi kısımlar sağlam?\n\n"
        "En fazla 400 kelimelik, keskin ve maddeler halinde bir çürütme yaz.\n\n"
        f"=== SENTEZ RAPORU ===\n{synthesis}"
    )
    return system, user


def _final_prompts(question: str, sfw: dict, synthesis: str, refutation: str):
    system = (
        f"Sen {sfw['name']} modelini ({sfw['thinkers']}) kullanan entegral bir filozofsun. "
        "Kendi sentezine yöneltilen çürütmeyi ciddiye alır, savunulamayan kısımları "
        "revize eder, savunulabilenleri gerekçesiyle korursun. "
        "Türkçe yazarsın, markdown başlıkları ve **kalın** vurgular kullanabilirsin."
    )
    user = (
        f'Soru: "{question}"\n\n'
        "Aşağıda önceki sentezin ve ona yöneltilmiş çürütme var. NİHAİ yanıtı yaz:\n"
        "1. Çürütmenin haklı olduğu noktaları açıkça kabul et ve düzelt\n"
        "2. Haksız olduğu noktalarda sentezi gerekçesiyle savun\n"
        "3. Revize edilmiş, kendi başına okunabilir NİHAİ sentezi sun\n"
        "4. Sonuna 'Epistemik Durum' başlıklı kısa bir bölüm ekle: bu yanıtın "
        "güven düzeyi, çözülmemiş gerilimler ve hangi yeni bilginin fikrini "
        "değiştirebileceği\n\n"
        "En az 600 kelimelik nihai rapor yaz.\n\n"
        f"=== ÖNCEKİ SENTEZ ===\n{synthesis}\n\n"
        f"=== ÇÜRÜTME ===\n{refutation}"
    )
    return system, user


# ── Pipeline yürütücü ────────────────────────────────────────────────────────

def _stream_stage(client, idx: int, system: str, user: str, msg_queue: queue.Queue,
                  max_tokens: int = 4000) -> str:
    """Tek bir aşamayı token-token akıtır, tam çıktıyı döner."""
    collected = []
    with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=TEMPERATURE,
        # Sabit system prompt'ları cache'le (paralel savunucular aynı system'i paylaşır)
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    ) as stream:
        for text in stream.text_stream:
            collected.append(text)
            msg_queue.put({"type": "delta", "task_index": idx, "text": text})
    return "".join(collected)


def run_pipeline_thread(question: str, msg_queue: queue.Queue, frameworks: dict = None):
    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        client = anthropic.Anthropic(api_key=api_key)

        fw = frameworks or DEFAULT_FRAMEWORKS
        rfw = FRAMEWORKS.get(fw.get("research", "analytic"), FRAMEWORKS["analytic"])
        cfw = FRAMEWORKS.get(fw.get("critique", "impartial_spectator"), FRAMEWORKS["impartial_spectator"])
        sfw = FRAMEWORKS.get(fw.get("synthesis", "aqal"), FRAMEWORKS["aqal"])

        # 0) Pozisyon haritası (akışsız)
        msg_queue.put({"type": "phase", "label": "Karşıt pozisyonlar belirleniyor…"})
        positions = _map_positions(client, question)
        msg_queue.put({"type": "pipeline", "stages": _stage_defs(rfw, cfw, sfw, positions),
                       "positions": positions})

        outputs = [""] * 6

        # 1-2) Paralel steelman savunucular
        msg_queue.put({"type": "status", "agent": 0, "status": "running"})
        msg_queue.put({"type": "status", "agent": 1, "status": "running"})

        def _run_advocate(i: int):
            sys_p, usr_p = _advocate_prompts(
                question, rfw, positions[i], positions[1 - i])
            outputs[i] = _stream_stage(client, i, sys_p, usr_p, msg_queue, 3000)
            msg_queue.put({"type": "task_complete", "task_index": i,
                           "output": outputs[i]})

        threads = [threading.Thread(target=_run_advocate, args=(i,), daemon=True)
                   for i in (0, 1)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 3) Kör eleştiri
        msg_queue.put({"type": "status", "agent": 2, "status": "running"})
        sys_p, usr_p = _critic_prompts(question, cfw, outputs[0], outputs[1], positions)
        critique = _stream_stage(client, 2, sys_p, usr_p, msg_queue, 3500)
        outputs[2] = critique
        msg_queue.put({"type": "task_complete", "task_index": 2, "output": critique})

        # 3b) Objektiflik rubriği (ayrı, akışsız çağrı — başarısızlığı pipeline'ı durdurmaz)
        try:
            rubric = _rubric_call(client, question, outputs[0], outputs[1],
                                  critique, positions)
            msg_queue.put({"type": "rubric", "data": rubric})
        except Exception as rub_exc:
            print(f"[rubric] atlandı: {type(rub_exc).__name__}: {rub_exc}", flush=True)

        # 4) Sentez
        msg_queue.put({"type": "status", "agent": 3, "status": "running"})
        sys_p, usr_p = _synth_prompts(question, sfw, outputs[0], outputs[1],
                                      critique, positions)
        outputs[3] = _stream_stage(client, 3, sys_p, usr_p, msg_queue, 3500)
        msg_queue.put({"type": "task_complete", "task_index": 3, "output": outputs[3]})

        # 5) Çürütme
        msg_queue.put({"type": "status", "agent": 4, "status": "running"})
        sys_p, usr_p = _refuter_prompts(question, outputs[3])
        outputs[4] = _stream_stage(client, 4, sys_p, usr_p, msg_queue, 1500)
        msg_queue.put({"type": "task_complete", "task_index": 4, "output": outputs[4]})

        # 6) Nihai sentez (revizyon)
        msg_queue.put({"type": "status", "agent": 5, "status": "running"})
        sys_p, usr_p = _final_prompts(question, sfw, outputs[3], outputs[4])
        outputs[5] = _stream_stage(client, 5, sys_p, usr_p, msg_queue, 3500)
        msg_queue.put({"type": "task_complete", "task_index": 5, "output": outputs[5]})

        msg_queue.put({"type": "done"})

    except Exception as exc:
        msg_queue.put({"type": "error", "message": str(exc)})


# ── SSE endpoint ─────────────────────────────────────────────────────────────

MAX_QUESTION_LEN = 500


@app.route("/api/run", methods=["POST"])
def run_pipeline():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    frameworks = data.get("frameworks") or DEFAULT_FRAMEWORKS

    if not question:
        return jsonify({"error": "Soru boş olamaz"}), 400
    if len(question) > MAX_QUESTION_LEN:
        return jsonify({"error": f"Soru {MAX_QUESTION_LEN} karakteri aşamaz"}), 400

    msg_queue: queue.Queue = queue.Queue()

    threading.Thread(
        target=run_pipeline_thread,
        args=(question, msg_queue, frameworks),
        daemon=True,
    ).start()

    def stream():
        while True:
            msg = msg_queue.get()
            yield f"data: {json.dumps(msg)}\n\n"
            if msg["type"] in ("done", "error"):
                break

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Chat endpoint (token streaming) ──────────────────────────────────────────

CHAT_SYSTEM = """Sen derin ve meraklı bir felsefe asistanısın. Türkçe yanıt verirsin.

Uzmanlık alanların:
- Epistemoloji (bilginin doğası, kaynakları, sınırları)
- Ontoloji (varlık, gerçeklik, bilinç)
- Etik (ahlak, özgür irade, sorumluluk)
- Matematik felsefesi (Platonizm, formalizm, keşif/icat tartışması)
- Ken Wilber'ın Integral Theory ve AQAL modeli
- Adam Smith'in ahlak felsefesi
- Wittgenstein, Gödel, Tegmark, Penrose

Yanıt verirken:
- Soyut kavramları somut örneklerle açıkla
- Birden fazla perspektifi dengeli sun
- "Bilmiyorum" ya da "tartışmalı" demekten çekinme
- Kısa ve öz ol; soru karmaşıklaştıkça derinleş
- Markdown kullanabilirsin (**kalın**, *italik*)"""


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])

    if not messages:
        return jsonify({"error": "Mesaj boş"}), 400

    # Sadece son 20 mesajı tut (token limitini aş önle)
    messages = messages[-20:]

    def stream():
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

            with client.messages.stream(
                model=MODEL,
                max_tokens=1024,
                system=CHAT_SYSTEM,
                messages=messages,
            ) as s:
                for text in s.text_stream:
                    yield f"data: {json.dumps({'delta': text})}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7070))
    print(f"\n🔭  Felsefi Araştırma Sistemi başlatılıyor...")
    print(f"    http://localhost:{port}\n")
    app.run(debug=False, port=port, threaded=True)
