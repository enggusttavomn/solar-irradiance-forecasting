> Registro da auditoria anterior. Para o escopo atual dos pseudocódigos e a remoção das inclusões de XGBoost, consulte [ajuste de foco](ajuste_de_foco.md).

# Auditoria de referencias e citacoes ? revista unificada

Data: 2026-09-07. Escopo: `artigos/revista_unificado/references.bib` e usos em arquivos `.tex`, incluindo secoes, tabelas e apendices. Esta auditoria nao altera os numeros experimentais nem sincroniza por si so o projeto remoto do Overleaf.

## Resultado verificavel

- 52 registros originais auditados; os 38 DOIs originais resolveram metadados depositados no Crossref.
- Corrigidos seis registros de autoria, normalizadas as iniciais de Ahmed2020, completado o titulo IRENA2014, substituida a URL Ford por divulgacao oficial persistente, ajustado o enquadramento de TimesNet e acrescentadas duas referencias XGBoost. Total atual: 54.
- Fotografia das citacoes apos essas inclusoes: 51 chaves usadas, nenhuma chave sem referencia e nenhuma chave duplicada. Tres registros nao usados foram preservados: `ajith2023`, `salinas2020` e `iea2023lowemissions`.
- Evidencia de metadados e campos originais: `.codex_review_crossref_20260907.json`. Mapa de usos: `.codex_review_citation_usage_20260907.json`.
- Confirmar metadados nao equivale a ler integralmente todos os artigos. O inventario abaixo diferencia evidencia editorial, resumo/texto acessivel e limites de acesso.

## Alteracoes aplicadas somente a references.bib

| Chave | Correcao |
|---|---|
| voyant2022 | Autores corretos: Cyril Voyant, Gilles Notton, Jean-Laurent Duchaud, Luis Antonio Garcia Gutierrez, Jamie M. Bright e Dazhi Yang. Removidos autores de outro trabalho erroneamente associados. |
| jung2020 | Yoonhwa Jung, Jaehoon Jung, Byungil Kim e SangUk Han substituem quatro prenomes incorretos. |
| ozoegwu2019 | Chigbogu Godwin Ozoegwu substitui Chigbo G. Ozoegwu. |
| guariso2020 | Matteo Sangiorgio substitui Maurizio Sangiorgio. |
| zhu2024 | Xun Ma e Reda Hassanien Emam Hassanien substituem Xiaojun Ma e Rania H. E. Hassanien. |
| yang2020verification | Nome de Frimane corrigido para Azeddine com A circunflexo, conforme deposito dos autores e Crossref. |
| wu2023 | `@inproceedings` e `booktitle` conforme BibTeX dos autores; protegida capitalizacao TimesNet/2D. |
| chen2016xgboost | Adicionada referencia fundadora de Chen e Guestrin, KDD 2016, p. 785--794, DOI 10.1145/2939672.2939785. |
| xgboostmultioutput | Adicionada documentacao oficial da familia 3.2 sobre folhas vetoriais e estrategia multi_output_tree. |

## Ajustes de texto encaminhados ao responsavel pelo manuscrito

1. Citacao can?nica XGBoost estava ausente. Citar `chen2016xgboost` ao apresentar o comparador; citar `xgboostmultioutput` para `hist`/`multi_output_tree`, que o artigo de 2016 nao documenta.
2. Em `sections/06_metrics.tex`, a formula de R2 e matematicamente correta, mas nao foi localizada como definicao explicita em Yang et al. 2020. Usar uma referencia especifica ou apresenta-la como definicao operacional do estudo. A documentacao oficial confirma o caso do previsor constante, valores negativos e referencia constante: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.r2_score.html .
3. Na mesma secao, Voyant et al. 2022, eq. 19, sustenta nRMSE normalizado pela media. A instabilidade quando a media tende a zero e uma consequencia algebrica da definicao; mover a citacao para a normalizacao, sem atribuir ao artigo uma conclusao que seu trecho sobre denominadores discute para MASE.
4. Em `tables/literature_review.tex`, linha Huang2021: explicitar que o modelo usa, alem do historico, temperatura, umidade e vento previstos para T+1. Fonte: https://www.sciencedirect.com/science/article/pii/S0960148121003402 .
5. Hochreiter/Schmidhuber 1997 e fonte de LSTM; a possibilidade de trocar celulas de uma DilatedRNN (RNN/GRU/LSTM) e sustentada por Chang2017. A citacao de Chang no inicio do paragrafo ajuda, mas pode ser repetida junto dessa afirmacao.

## Checagem tecnica XGBoost

Fonte matematica: https://arxiv.org/pdf/1603.02754 , secoes 2.1--2.3, eqs. 2--7. Modelo escalar com penalidade L2: Omega(f)=gamma*T+(lambda/2)*sum(w_j^2); g e h sao derivadas da perda em relacao ao escore atual; w_j=-G_j/(H_j+lambda). Ganho liquido = 0.5*[G_L^2/(H_L+lambda)+G_R^2/(H_R+lambda)-(G_L+G_R)^2/(H_L+H_R+lambda)]-gamma. Se gamma ja foi subtraido, comparar ganho com zero; aplicar shrinkage eta apenas uma vez. Essas formulas escalares nao devem ser apresentadas como uma implementacao completa de folhas vetoriais sem explicitar a extensao multiobjetivo.

A documentacao em https://xgboost.readthedocs.io/en/release_3.2.0/tutorials/multioutput.html confirma folhas com uma componente por alvo para `multi_output_tree` e exige distinguir isso de um modelo separado por alvo. A pagina identifica a funcionalidade como experimental; isso deve ser registrado como limitacao tecnica se pertinente a reproducao, sem inventar garantias de equivalencia com 2016.

## Inventario de todos os registros

O link DOI identifica a publicacao e os metadados registrados. Quando existe evidencia primaria adicional usada nesta revisao, ela aparece na mesma linha. Os usos exatos por arquivo/linha estao no JSON de usos.

| Chave | Fonte(s) | Resultado e limite |
|---|---|---|
| `antonanzas2016` | [DOI](https://doi.org/10.1016/j.solener.2016.06.069) | Metadados conferidos. Revisao adequada para distinguir horizonte, tarefa e entradas; nao usada como prova de desempenho proprio. |
| `voyant2017` | [DOI](https://doi.org/10.1016/j.renene.2016.12.095) | Metadados conferidos. Escopo de revisao de metodos corresponde a contextualizacao. |
| `yang2018` | [DOI](https://doi.org/10.1016/j.solener.2017.11.023) | Metadados conferidos; ano de fasciculo 2018 correto apesar do DOI conter 2017. |
| `wu2023` | [Pagina oficial](https://openreview.net/forum?id=ju_Uqw384Oq), [Fonte primaria](https://github.com/thuml/TimesNet) | Autores e ICLR 2023 confirmados pelo repositorio dos autores. Corrigido tipo para inproceedings; preservada chave. |
| `chang2017` | [Pagina oficial](https://proceedings.neurips.cc/paper_files/paper/2017/hash/32bb90e8976aab5298d5da10fe66f21d-Abstract.html) | Anais NeurIPS 30, autores e paginas 77--87 confirmados. Sustenta recorrencia dilatada e flexibilidade de celulas. |
| `duffie2013` | [Fonte primaria](https://sel.me.wisc.edu/publications.shtml) | Wiley e laboratorio dos autores confirmam autores, quarta edicao e abril de 2013. |
| `sengupta2018` | [DOI](https://doi.org/10.1016/j.rser.2018.03.003) | Metadados conferidos. Fonte correta para natureza fisica/modelada da NSRDB; v4 documentada separadamente em nlr2026. |
| `voyant2022` | [DOI](https://doi.org/10.1016/j.renene.2022.04.065), [Fonte primaria](https://arxiv.org/abs/2203.14959) | AUTORIA CORRIGIDA. Preprint dos autores e editora confirmam cinco referencias simples mais combinacao e dependencia do horizonte. |
| `montero2021` | [DOI](https://doi.org/10.1016/j.ijforecast.2021.03.004) | Metadados conferidos. Fonte pertinente para previsores locais/globais; compartilhamento nao garante ganho por local. |
| `hyndman2006` | [DOI](https://doi.org/10.1016/j.ijforecast.2006.03.001) | Metadados conferidos. Fonte adequada para MAE, RMSE e limites de medidas percentuais. |
| `diagne2013` | [DOI](https://doi.org/10.1016/j.rser.2013.06.042) | Metadados conferidos. Revisao pertinente a classificacao por horizonte e tipo de entrada. |
| `inman2013` | [DOI](https://doi.org/10.1016/j.pecs.2013.06.002) | Metadados conferidos. Revisao pertinente a integracao de previsao solar e horizontes operacionais. |
| `ahmed2020` | [DOI](https://doi.org/10.1016/j.rser.2020.109792), [Fonte primaria](https://research-repository.uwa.edu.au/en/publications/a-review-and-evaluation-of-the-state-of-the-art-in-pv-solar-power) | Metadados e resumo no repositorio UWA conferidos. Autores normalizados exatamente como na fonte primaria: R. Ahmed, V. Sreeram, Y. Mishra e M. D. Arif; removidas expansoes nao certificadas. |
| `chu2021` | [DOI](https://doi.org/10.1016/j.isci.2021.103136) | Metadados conferidos. Revisao de intra-hour compatibiliza escopo e discussao geral. |
| `lin2023` | [DOI](https://doi.org/10.1016/j.ijforecast.2021.11.002) | Metadados conferidos. Ano 2023 de fasciculo correto, embora DOI contenha 2021; foco especifico em imagens do ceu. |
| `ajith2023` | [DOI](https://doi.org/10.1016/j.rser.2023.113362) | Metadados conferidos. Registro nao citado no .tex desta fotografia; preservado. |
| `cheng2021` | [DOI](https://doi.org/10.1016/j.renene.2021.08.038) | Metadados e resumo da editora confirmam CNN/LSTM, horizontes dia--semana e temperatura/umidade/chuva observadas ou previstas. Detalhes finos de arquitetura/experimento limitado nao certificados por leitura integral. |
| `huang2021` | [DOI](https://doi.org/10.1016/j.renene.2021.02.161), [Fonte primaria](https://www.sciencedirect.com/science/article/pii/S0960148121003402) | Metadados e metodologia da editora confirmam WPD/CNN/LSTM/MLP, Denver/Clark/Folsom, 24 h de historico e 1 h a frente. Inclui tambem previsoes meteorologicas T+1: explicitar na tabela. |
| `zhao2024timesnet` | [DOI](https://doi.org/10.1016/j.renene.2023.119706) | Metadados e resumo confirmam ICEEMDAN + TimesNet e previsao horaria de uma semana. Ano 2024 do fasciculo correto, embora DOI contenha 2023. |
| `yang2020verification` | [DOI](https://doi.org/10.1016/j.solener.2020.04.019), [Fonte primaria](https://escholarship.org/content/qt6w14r65n/qt6w14r65n.pdf) | GRAFIA DE FRIMANE CORRIGIDA. Texto integral dos autores confirma pratica de verificacao, referencias, MSE e correlacao; definicao especifica de R2 nao localizada. |
| `hochreiter1997` | [DOI](https://doi.org/10.1162/neco.1997.9.8.1735) | Metadados conferidos. Fonte fundadora da LSTM; isoladamente nao e fonte de GRU. |
| `hewamalage2021` | [DOI](https://doi.org/10.1016/j.ijforecast.2020.06.008) | Metadados conferidos. Revisao pertinente a recorrencia e desenho de previsao temporal. |
| `salinas2020` | [DOI](https://doi.org/10.1016/j.ijforecast.2019.07.001) | Metadados conferidos. Registro nao citado no .tex desta fotografia; preservado. |
| `jung2020` | [DOI](https://doi.org/10.1016/j.jclepro.2019.119476) | QUATRO PRENOMES CORRIGIDOS. Fonte e metadados confirmam previsao de potencia PV com sequencias mensais; nao equivale a GHI. |
| `ozoegwu2019` | [DOI](https://doi.org/10.1016/j.jclepro.2019.01.096) | NOME DO AUTOR CORRIGIDO. Resumo confirma NAR, NARX, hibrido e numero do mes; alvo e media mensal da radiacao diaria. |
| `guariso2020` | [DOI](https://doi.org/10.3390/en13153987), [Fonte primaria](https://www.mdpi.com/1996-1073/13/15/3987/notes) | PRENOME DE SANGIORGIO CORRIGIDO. Editora confirma FF/LSTM, estrategias recursiva/multi-modelo/multi-saida e 1--12 h. |
| `zhu2024` | [DOI](https://doi.org/10.1016/j.enconman.2024.118758), [Fonte primaria](https://www.sciencedirect.com/science/article/abs/pii/S019689042400699X) | DOIS NOMES CORRIGIDOS. Editora confirma TimesNet/Informer/Transformer/Pyraformer, nove horizontes 10 min--24 h, estacoes e diferentes volumes de treino. |
| `cabral2026` | [DOI](https://doi.org/10.1016/j.solener.2026.114964) | Metadados e texto disponibilizado pela editora confirmam GPT-Neo, GHI e 40 locais. Volume 317 previsto para outubro de 2026: artigo ja tem DOI e conteudo online; nao alterar ano. |
| `anderson2023` | [DOI](https://doi.org/10.21105/joss.05994) | Metadados JOSS confirmados; referencia correta da atualizacao pvlib. |
| `nlr2026` | [Pagina oficial](https://developer.nlr.gov/docs/solar/nsrdb/nsrdb-GOES-aggregated-v4-0-0-download/) | Pagina oficial confirma GOES Aggregated PSM v4.0.0, 4 km, base de 30 min e opcao de download em 60 min. |
| `chow2011` | [DOI](https://doi.org/10.1016/j.solener.2011.08.025), [Fonte primaria](https://escholarship.org/content/qt5813b9j0/qt5813b9j0.pdf) | Manuscrito depositado pelos autores confirma imagens de 30 s, seis piranometros e quatro dias parcialmente nublados; limites da pequena validacao devem ser preservados. |
| `chen2020cloudramps` | [DOI](https://doi.org/10.1016/j.apenergy.2020.114980) | Metadados conferidos. Fonte pertinente para rampas PV sob passagem de nuvens; nao sustenta inferir precipitacao de GHI. |
| `hersbach2020` | [DOI](https://doi.org/10.1002/qj.3803) | Metadados conferidos. Fonte pertinente a natureza e limitacoes de reanalise ERA5. |
| `copernicus2026era5` | [Pagina oficial](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-timeseries) | Catalogo confirma titulo, publicacao 2025-03-17 e grade atmosferica 0.25 graus. Em 2026-09-07 a pagina mostra atualizacao 2026-09-07; nota antiga pode registrar fotografia historica. DOI adicional disponivel: 10.24381/1cf1ad76. |
| `beck2018` | [DOI](https://doi.org/10.1038/sdata.2018.214) | Metadados conferidos; fonte adequada ao mapa nominal de 1 km. A classificacao dos dez pontos depende da auditoria dos arquivos locais. |
| `ipcc2022energy` | [DOI](https://doi.org/10.1017/9781009157926.008) | DOI, titulo e paginas confirmados no registro. Crossref data a edicao Cambridge em 2023, mas citacao recomendada do relatorio e 2022; preservado 2022. |
| `iea2023lowemissions` | [Pagina oficial](https://www.iea.org/reports/low-emissions-sources-of-electricity) | Pagina oficial confirma titulo, data 2023-09-26 e citacao. Nao citado no .tex desta fotografia. |
| `irena2024weto` | [Pagina oficial](https://www.irena.org/publications/2024/Nov/World-Energy-Transitions-Outlook-2024) | Pagina oficial indexada confirma titulo, ISBN 978-92-9260-634-3, novembro de 2024 e eletrificacao/eficiencia. Acesso direto retornou 403. |
| `nijsse2023` | [DOI](https://doi.org/10.1038/s41467-023-41971-7) | Metadados conferidos. Texto descreve resultados de cenarios, nao uma garantia deterministica; redacao do manuscrito ja faz essa distincao. |
| `luderer2022` | [DOI](https://doi.org/10.1038/s41560-021-00937-z) | Metadados conferidos. Ano 2022 do volume 7 correto, com publicacao online em novembro de 2021. |
| `ipcc2022industry` | [DOI](https://doi.org/10.1017/9781009157926.013) | DOI, titulo e paginas confirmados. Mesmo desfasamento 2022 do relatorio/2023 da edicao Cambridge; preservado 2022. |
| `rissman2020` | [DOI](https://doi.org/10.1016/j.apenergy.2020.114848) | Metadados conferidos. Fonte adequada a diversidade de estrategias industriais; manter cautela com expansao/inversao de nomes em metadados. |
| `madeddu2020` | [DOI](https://doi.org/10.1088/1748-9326/abbd02) | Metadados conferidos. Fonte pertinente a eletrificacao direta de calor industrial; nao sustenta substituicao de todo uso energetico por PV. |
| `padmanathan2018` | [DOI](https://doi.org/10.1016/j.jii.2018.01.003) | Metadados conferidos. Fonte pertinente a integracao solar industrial/comercial; convencoes de nomes indianos nao alteradas por inferencia. |
| `dhingra2023` | [DOI](https://doi.org/10.1016/j.solener.2023.02.056) | Metadados conferidos. Estudo sobre barreiras indianas; o manuscrito formula barreiras dependentes do local, sem extrapolar resultados quantitativos. |
| `irena2014manufacturing` | [Pagina oficial](https://www.irena.org/publications/2014/Jun/Renewable-Energy-in-Manufacturing) | PDF oficial de 36 paginas baixado e conferido. Titulo completado com subtitulo A technology roadmap for REmap 2030; folha de rosto confirma junho de 2014. |
| `eu2024epbd` | [Pagina oficial](https://eur-lex.europa.eu/eli/dir/2024/1275/oj), [Fonte primaria](https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX%3A32024L1275) | Texto oficial confirma artigo 10, implantacao faseada e condicoes de adequacao tecnica/economica/funcional. Manuscrito delimita corretamente jurisdicao UE. |
| `nestle2024biometano` | [Pagina oficial](https://www.nestle.com.br/media/pressreleases/allpressreleases/nestle-inicia-utilizacao-de-biometano-em-operacoes-no-brasil) | Fonte oficial confirma KitKat em Cacapava majoritariamente solar. Cabecalho 29 nov 2024, corpo datado 13 nov; preservada data do cabecalho. |
| `mercedesfactory56` | [Pagina oficial](https://group.mercedes-benz.com/company/mercedes-benz-energy/news/factory-56.html) | Fonte oficial confirma titulo The future of production, PV no telhado e armazenamento. Sem data editorial clara: n.d. preservado. |
| `tesla2021impact` | [Pagina oficial](https://www.tesla.com/ns_videos/2021-tesla-impact-report.pdf) | Relatorio 2021 publicado em 2022 localizado em dominio oficial. Trecho primario indexado Covering roof space with solar panels confirma PV nos telhados de Nevada, Nova York e instalacoes na California, sustentando a afirmacao do manuscrito. Downloads diretos retornam 403; nao houve leitura integral certificada. |
| `ford2023valencia` | [Pagina oficial](https://www.fordpresse.be/fr/nouvelles/ford-announces-new-solar-power-plant-as-further-step-towards-achieving-ambitious-sustainability-targets-5768/) | URL substituida pela mesma divulgacao em ingles no Ford Press Belux (Ford Motor Company Belgium); pagina acessivel e PDF oficial de duas paginas baixado, confirmando planta solar Almussafes/Valencia. Data 17 jan 2023 confirmada no cabecalho da pagina. |
| `nasapowerdaily` | [Pagina oficial](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) | Documentacao oficial confirma API diaria e tempo solar local/UTC. Fonte dos dados, nao dos limiares autorais 1 mm/dia e 80%. |
| `chen2016xgboost` | [DOI](https://doi.org/10.1145/2939672.2939785), [Fonte primaria](https://github.com/dmlc/xgboost/blob/master/CITATION) | ADICIONADO. CITATION oficial confirma Chen/Guestrin, KDD 2016, 785--794 e DOI; nao cobre a estrategia moderna multi_output_tree. |
| `xgboostmultioutput` | [Pagina oficial](https://xgboost.readthedocs.io/en/release_3.2.0/tutorials/multioutput.html) | ADICIONADO. Documentacao oficial release 3.2 explica hist + multi_output_tree, folhas vetoriais e distingue one_output_per_tree. |

## Limites que impedem declarar tudo certificado

- O acesso direto a alguns textos da Elsevier, MDPI, IPCC, IRENA, Tesla e OpenReview retornou 403, verificacao de navegador ou erro de extracao. Foram usados metadados registrados, repositorios dos autores e trechos indexados das paginas primarias quando disponiveis. Nao houve leitura integral certificada de todos os 52 registros.
- Ahmed2020: resolvido mediante uso das iniciais publicadas pela fonte primaria, sem expansoes inferidas.
- Ford: resolvido. URL substituida por pagina oficial persistente; PDF e HTML guardados em `.codex_review_external_sources_20260907`.
- A publicacao 2025 e a atualizacao 2026 do catalogo ERA5 sao datas distintas. Uma chave BibTeX contendo 2026 nao implica que o campo year=2025 esteja errado. A data de consulta 2026-08-25 nas referencias anteriores registra uma consulta passada e nao foi reescrita automaticamente.
- As caracteristicas exatas de arquiteturas, dados, janelas, protocolos e resultados do estudo sao objeto da auditoria de codigo/dados feita pelos demais responsaveis, nao prova derivada da bibliografia.

## Refinamento final de fontes institucionais

- Ahmed2020 passou a registrar as iniciais exatamente publicadas no [repositorio da UWA](https://research-repository.uwa.edu.au/en/publications/a-review-and-evaluation-of-the-state-of-the-art-in-pv-solar-power).
- IRENA2014 recebeu o subtitulo completo confirmado na folha de rosto do [PDF oficial](https://www.irena.org/-/media/Files/IRENA/Agency/Publication/2014/IRENA_REmap-2030-Renewable-Energy-in-Manufacturing.pdf).
- Ford2023valencia preserva a chave, mas aponta agora para a [divulgacao inglesa oficial](https://www.fordpresse.be/fr/nouvelles/ford-announces-new-solar-power-plant-as-further-step-towards-achieving-ambitious-sustainability-targets-5768/). O [PDF oficial](https://www.fordpresse.be/content/documents/news/2023/2023_01_17_valencia_solar_plant_en.pdf) foi baixado e seu conteudo solar conferido. A pagina publica a data 17/01/2023; o PDF contem o marcador editorial Jan. XX, portanto a data precisa vem do HTML, nao do marcador do PDF.
- A afirmacao Tesla do manuscrito foi conferida em texto indexado do proprio [PDF oficial](https://www.tesla.com/ns_videos/2021-tesla-impact-report.pdf), secao Covering roof space with solar panels: instala PV nos telhados de fabricas nomeadas. A limitacao restante e somente de acesso ao PDF integral, cujo download HTTP retornou 403; nao de falta de sustentacao para a afirmacao especifica citada.
