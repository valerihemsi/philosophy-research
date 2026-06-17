"""
Felsefi Araştırma Sistemi — Flask sunucusu
Kullanım: python server.py
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
import threading
import warnings
warnings.filterwarnings("ignore")

app = Flask(__name__, static_folder=".")


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


# ── Ajan tanımları (doğrudan Anthropic SDK + streaming) ──────────────────────

AGENT_NAMES = ["Felsefi Araştırmacı", "Epistemik Eleştirmen", "Entegral Sentezci"]


def _build_agent_prompts(question: str, rfw: dict, cfw: dict, sfw: dict):
    """Her ajan için (system, user) çiftlerinin listesini döner. user metni
    önceki ajanların çıktıları runtime'da eklenince tamamlanır."""

    researcher_system = (
        f"Sen {rfw['name']} geleneğini ({rfw['thinkers']}) derinlemesine bilen "
        "ve bunu birincil araştırma yöntemi olarak kullanan bir filozofsun. "
        "Avrupa-merkezli düşünce tarihinin ötesine geçmeyi hedefliyorsun; "
        "Doğu, İslam, Hint ve Batı felsefi geleneklerini eşit ağırlıkta değerlendirirsin. "
        "Gücün bilgiyi nasıl şekillendirdiğini görmeye özellikle dikkat edersin. "
        "Türkçe yazarsın, markdown başlıkları ve **kalın** vurgular kullanabilirsin."
    )
    researcher_user = (
        f'"{question}" sorusunu felsefi perspektiften araştır.\n\n'
        f"=== KULLANILACAK ARAŞTIRMA ÇERÇEVESİ: {rfw['name'].upper()} ({rfw['thinkers']}) ===\n"
        f"{rfw['instruction']}\n\n"
        "=== ARAŞTIRMA EKSENLERİ ===\n"
        "Bu çerçeveyi birincil yöntem olarak kullanarak şunları ele al:\n"
        "1. Bu soruya verilen en güçlü yanıtlar ve karşı-argümanlar\n"
        "2. Tarihin farklı kültür ve dönemlerindeki düşünürlerin tutumları\n"
        "3. Sorunun sosyolojik ve güç-ilişkileri boyutu\n"
        "4. Seçilen çerçevenin bu soruya özgün katkısı nedir?\n"
        "5. Çözüme kavuşmamış gerilimler ve açık sorular\n"
        "6. Okuyucuya: Bu soruyu neden önemsemeli?\n\n"
        f"Çerçeve adını ({rfw['name']}) ve temel kavramlarını açıkça kullan. "
        "En az 700 kelimelik, bölümlere ayrılmış felsefi araştırma raporu yaz."
    )

    critic_system = (
        f"Sen {cfw['name']} metodolojisini ({cfw['thinkers']}) ustalıkla uygulayan "
        "bir epistemik hakemsin. Hiçbir tarafın bakış açısını önceden benimsemeden "
        "tüm argümanları eşit mesafeden değerlendirirsin. "
        "Bulgularını araştırmacıya karşı değil, epistemik dürüstlük adına ortaya koyarsın. "
        "Türkçe yazarsın, markdown başlıkları ve **kalın** vurgular kullanabilirsin."
    )
    critic_user_template = (
        f'Aşağıdaki araştırma raporunu, "{question}" sorusu bağlamında eleştir.\n\n'
        f"=== KULLANILACAK ELEŞTİRİ ÇERÇEVESİ: {cfw['name'].upper()} ({cfw['thinkers']}) ===\n"
        f"{cfw['instruction']}\n\n"
        "=== ELEŞTİRİ EKSENLERİ ===\n"
        "Bu çerçeveyi birincil yöntem olarak kullanarak şunları ele al:\n"
        "1. Araştırmacının çerçeve önyargıları — hangi pozisyona baştan eğilimli?\n"
        "2. Retorik ağırlık mekanizmaları — hangi argümanlar ne kadar yer aldı?\n"
        "3. Eksik sesler — hangi düşünürler, gelenekler veya yaklaşımlar dışlandı?\n"
        "4. Kavramsal boşluklar — tanımlanmayan ya da muğlak bırakılan terimler\n"
        "5. Araştırmacının en büyük kör noktası (tek paragraf)\n"
        "6. Seçilen eleştiri çerçevesi araştırmada ne buldu, ne bulamadı?\n\n"
        f"Çerçeve adını ({cfw['name']}) ve temel kavramlarını açıkça kullan. "
        "En az 500 kelimelik epistemik denetim raporu yaz.\n\n"
        "=== ARAŞTIRMACININ RAPORU ===\n"
        "{research_output}"
    )

    synth_system = (
        f"Sen {sfw['name']} modelini ({sfw['thinkers']}) derinlemesine bilen "
        "bir entegral filozofsun. Gerçekliğin birbirine indirgenemeyen boyutlarını "
        "bütünleştirmeyi görev sayarsın; hiçbir tekil bakış açısının tek başına "
        "yeterli olmadığını bilirsin. "
        "Türkçe yazarsın, markdown başlıkları ve **kalın** vurgular kullanabilirsin."
    )
    synth_user_template = (
        f'"{question}" sorusu bağlamında, aşağıdaki araştırma ve eleştiri raporlarını sentezle.\n\n'
        f"=== KULLANILACAK SENTEZ ÇERÇEVESİ: {sfw['name'].upper()} ({sfw['thinkers']}) ===\n"
        f"{sfw['instruction']}\n\n"
        "=== SENTEZ GÖREVİ ===\n"
        "Bu çerçeveyi birincil yöntem olarak kullanarak şunları ele al:\n"
        "1. Araştırma ve eleştiri raporlarındaki temel gerilimler ve çelişkiler\n"
        "2. Seçilen sentez çerçevesi bu gerilimleri nasıl dönüştürüyor?\n"
        f"3. {rfw['name']} + {cfw['name']} bulgularını {sfw['name']} içinde bütünleştir\n"
        "4. Hangi boyutlar her iki raporda da ihmal edildi?\n"
        "5. Sahte uzlaşıyı gerçek entegrasyondan ayıran kriter nedir?\n"
        "6. Kapanış: Bu soruyu sormaya devam etmenin önemi\n\n"
        f"Çerçeve adını ({sfw['name']}) ve temel kavramlarını açıkça kullan. "
        "En az 600 kelimelik entegral sentez raporu yaz.\n\n"
        "=== ARAŞTIRMACININ RAPORU ===\n"
        "{research_output}\n\n"
        "=== ELEŞTİRMENİN RAPORU ===\n"
        "{critique_output}"
    )

    return [
        (researcher_system, researcher_user),
        (critic_system, critic_user_template),
        (synth_system, synth_user_template),
    ]


def run_crew_thread(question: str, msg_queue: queue.Queue, frameworks: dict = None):
    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        client = anthropic.Anthropic(api_key=api_key)

        fw = frameworks or DEFAULT_FRAMEWORKS
        rfw = FRAMEWORKS.get(fw.get("research",  "analytic"),           FRAMEWORKS["analytic"])
        cfw = FRAMEWORKS.get(fw.get("critique",  "impartial_spectator"), FRAMEWORKS["impartial_spectator"])
        sfw = FRAMEWORKS.get(fw.get("synthesis", "aqal"),               FRAMEWORKS["aqal"])

        prompts = _build_agent_prompts(question, rfw, cfw, sfw)

        outputs = ["", "", ""]

        for idx, (system_prompt, user_template) in enumerate(prompts):
            if idx == 1:
                user_msg = user_template.replace("{research_output}", outputs[0])
            elif idx == 2:
                user_msg = (
                    user_template
                    .replace("{research_output}", outputs[0])
                    .replace("{critique_output}", outputs[1])
                )
            else:
                user_msg = user_template

            collected = []
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            ) as stream:
                for text in stream.text_stream:
                    collected.append(text)
                    msg_queue.put({
                        "type": "delta",
                        "task_index": idx,
                        "text": text,
                    })

            full_output = "".join(collected)
            outputs[idx] = full_output
            msg_queue.put({
                "type": "task_complete",
                "task_index": idx,
                "agent_name": AGENT_NAMES[idx],
                "output": full_output,
            })

        msg_queue.put({"type": "done"})

    except Exception as exc:
        msg_queue.put({"type": "error", "message": str(exc)})


# ── SSE endpoint ─────────────────────────────────────────────────────────────

@app.route("/api/run", methods=["POST"])
def run_crew():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    frameworks = data.get("frameworks") or DEFAULT_FRAMEWORKS

    if not question:
        return jsonify({"error": "Soru boş olamaz"}), 400

    msg_queue: queue.Queue = queue.Queue()

    threading.Thread(
        target=run_crew_thread,
        args=(question, msg_queue, frameworks),
        daemon=True,
    ).start()

    def stream():
        # Framework bilgisini UI'ya gönder
        rfw = FRAMEWORKS.get(frameworks.get("research",  "analytic"),           FRAMEWORKS["analytic"])
        cfw = FRAMEWORKS.get(frameworks.get("critique",  "impartial_spectator"), FRAMEWORKS["impartial_spectator"])
        sfw = FRAMEWORKS.get(frameworks.get("synthesis", "aqal"),               FRAMEWORKS["aqal"])
        yield f"data: {json.dumps({'type': 'frameworks', 'labels': [rfw['name'], cfw['name'], sfw['name']]})}\n\n"
        # İlk ajan başladı bildirimi
        yield f"data: {json.dumps({'type': 'status', 'agent': 0, 'status': 'running'})}\n\n"

        while True:
            msg = msg_queue.get()

            if msg["type"] == "task_complete":
                next_idx = msg["task_index"] + 1
                if next_idx < 3:
                    yield f"data: {json.dumps({'type': 'status', 'agent': next_idx, 'status': 'running'})}\n\n"
                yield f"data: {json.dumps(msg)}\n\n"

            elif msg["type"] in ("done", "error"):
                yield f"data: {json.dumps(msg)}\n\n"
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
                model="claude-sonnet-4-6",
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
