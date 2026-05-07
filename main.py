#!/usr/bin/env python
"""
Math Philosophy Crew — Çalıştırma giriş noktası

Kullanım:
    python main.py

Çıktılar:
    research_report.md  — Agent 1'in araştırma raporu
    bias_analysis.md    — Agent 2'nin Tarafsız Gözlemci analizi
"""
import warnings
warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from crew import MathPhilosophyCrew


def run():
    crew = MathPhilosophyCrew().crew()
    result = crew.kickoff()
    print("\n" + "=" * 60)
    print("CREW TAMAMLANDI")
    print("=" * 60)
    print(result)
    print("\nDosyalar oluşturuldu:")
    print("  • research_report.md  — Matematiksel çerçeve araştırması")
    print("  • bias_analysis.md    — Tarafsız Gözlemci bias analizi")


if __name__ == "__main__":
    run()
