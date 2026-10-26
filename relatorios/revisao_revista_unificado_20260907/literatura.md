# Sustentação dos estudos relacionados — 2026-09-07

Escopo: afirmações de `artigos/revista_unificado/sections/02_related_work.tex` e `tables/literature_review.tex` referentes aos dez estudos solicitados. Esta etapa somente relata evidências; as correções editoriais foram encaminhadas ao revisor principal.

## Ajustes indicados

1. **Huang (2021): informação futura disponível.** A introdução, etapa (6) do modelo, informa que o MLP recebe temperatura, umidade e vento da previsão meteorológica para T+1, além da saída da rede. A tabela deve distinguir essas previsões do histórico meteorológico. O título da primeira tabela, “observation-driven”, também deve admitir esse tipo de entrada. Arquitetura WPD–CNN–LSTM–MLP, três cidades, horizonte 1h e referências estão sustentados. [Artigo da editora](https://www.sciencedirect.com/science/article/pii/S0960148121003402).

2. **Chow (2011): natureza da avaliação.** Os valores 30s, quatro dias parcialmente nublados, seis piranômetros e previsão até5min foram confirmados no resumo e §2.1. Porém, a verificação quantitativa é das condições de nuvem. O §2.3 declara que GHI estimado é utilizado somente na avaliação qualitativa. Recomenda-se explicitar essa diferença na coluna de avaliação e distinguir o nowcast de nuvens da extrapolação até5min. [Manuscrito dos autores, repositório UCSD](https://escholarship.org/content/qt5813b9j0/qt5813b9j0.pdf), páginas 2,4 e9 do PDF incluindo a capa do repositório.

3. **Zhao (2024): entrada meteorológica omitida.** A contribuição(2) informa que sequências de irradiância decompostas com ICEEMDAN são combinadas com dados meteorológicos na TimesNet. Portanto, a descrição das entradas precisa incluir meteorologia. O trecho experimental confirma contexto48h e horizontes24,48,96,168h. O título usa “irradiation”, enquanto o resumo e método descrevem “irradiance”; não se inferiu a unidade de energia apenas pelo título. [Artigo da editora](https://www.sciencedirect.com/science/article/abs/pii/S096014812301621X).

4. **Ozoegwu (2019): exógena é especificamente o mês.** A introdução define e(t) como número do mês: NARX usa seus valores defasados; o híbrido usa o mês corrente. “Month number, and exogenous series” pode sugerir entradas adicionais que não estão presentes. Recomenda-se descrever histórico de radiação e essas duas codificações do mês. NAR/NARX/híbrido e alvo mensal estão confirmados; o híbrido foi empregado até dois anos adiante. [Artigo da editora](https://www.sciencedirect.com/science/article/abs/pii/S0959652619301076).

5. **Cheng (2021): saídas diurnas.** Os experimentos organizam dez leituras horárias por dia, no período08–18h. “Daytime hourly irradiance” explicita melhor o suporte do alvo. Demais pontos conferem: Taiwan, CNN1D/LSTM/concatenação/densa, treinamento limitado e temperatura/umidade/chuva observadas e previstas; horizonte até7dias. [Artigo da editora](https://www.sciencedirect.com/science/article/abs/pii/S096014812101199X).

## Afirmações conferidas sem problema material

- **Guariso (2020):** histórico24h; horizontes1–12h; estratégias FF recursiva, multi-modelo e multi-output, além de LSTM; persistência, persistência24h e céu limpo; desenvolvimento em Como e transferência para três estações sem retreino. A tabela e a narrativa estão sustentadas. [Artigo MDPI](https://www.mdpi.com/1996-1073/13/15/3987), §§2.1,3.1,3.2.
- **Voyant (2022):** cinco métodos de referência mais uma combinação, totalizando seis; ARTU é de ordem2; previsão direta de múltiplos passos, quase nenhum histórico, ausência de etapa de treinamento e dados de múltiplos climas. [Manuscrito dos autores](https://arxiv.org/pdf/2203.14959), highlights, resumo e §2.
- **Zhu (2024):** TimesNet/Informer/Transformer/Pyraformer; nove horizontes10,20,30,40,50,60min e6,12,24h; cinco volumes de treinamento, quatro estações e combinações meteorológicas em estufa fotovoltaica. [Artigo da editora](https://www.sciencedirect.com/science/article/abs/pii/S019689042400699X).
- **Cabral (2026):** GPT-Neo, somente GHI,40localidades, diversos climas, horizonte de vários anos e avaliação computacional. [Artigo da editora](https://www.sciencedirect.com/science/article/pii/S0038092X26006535), resumo, highlights e desenho experimental.
- **Jung (2020):** LSTM para geração PV em resolução mensal,164plantas e aplicação a novos locais; a distinção em relação ao alvo GHI do artigo unificado é correta. [Artigo da editora](https://www.sciencedirect.com/science/article/pii/S095965261934346X), introdução.

## Limites da checagem

Chow e Voyant foram consultados em PDFs dos próprios autores. Para os demais, os trechos primários pertinentes estavam disponíveis nas páginas das editoras ou em sua indexação de busca. Algumas aberturas diretas de DOI/ScienceDirect/MDPI deram403/429, embora a busca retornasse os trechos necessários. Não se alegou acesso ao PDF integral de todos os estudos, nem validação independente dos experimentos externos. As correções acima se limitam ao que as fontes consultadas sustentam.
