from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent

claude = LLM(model="anthropic/claude-sonnet-4-6")


@CrewBase
class MathPhilosophyCrew:
    """
    Üç agentlı epistemik araştırma sistemi:
    - Agent 1: Matematik felsefesini araştırır (keşif mi icat mı?)
    - Agent 2: Adam Smith Tarafsız Gözlemci yöntemiyle araştırmadaki biasları tespit eder
    - Agent 3: Ken Wilber'ın Dört Kadran modeliyle tüm araştırmayı sentezler
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    @agent
    def math_framework_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["math_framework_researcher"],
            llm=claude,
            verbose=True,
        )

    @agent
    def impartial_spectator(self) -> Agent:
        return Agent(
            config=self.agents_config["impartial_spectator"],
            llm=claude,
            verbose=True,
        )

    @agent
    def integral_synthesizer(self) -> Agent:
        return Agent(
            config=self.agents_config["integral_synthesizer"],
            llm=claude,
            verbose=True,
        )

    @task
    def research_mathematical_frameworks(self) -> Task:
        return Task(
            config=self.tasks_config["research_mathematical_frameworks"],
        )

    @task
    def bias_and_weight_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["bias_and_weight_analysis"],
        )

    @task
    def four_quadrants_synthesis(self) -> Task:
        return Task(
            config=self.tasks_config["four_quadrants_synthesis"],
        )

    @crew
    def crew(self) -> Crew:
        # Sequential: 1 → 2 → 3
        # Agent 3, hem araştırmayı hem bias raporunu context olarak alır.
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
