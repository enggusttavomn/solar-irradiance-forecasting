# Codigo-fonte

Use as subpastas abaixo para estudar o projeto na ordem do fluxo cientifico:

1. `coleta/`: API NSRDB e cadastro das localidades;
2. `preparacao/`: limpeza, agregacao e base mensal;
3. `modelos/`: um arquivo publico para cada um dos dez metodos;
4. `experimento/`: orquestracao, metricas e reprodutibilidade;
5. `visualizacao/`: figuras oficiais.

Alguns modulos historicos ainda aparecem diretamente nesta pasta, como
`experimento_mensal_canonico.py` e `modelos_globais_gluonts.py`. Eles sao os
motores exatos usados na execucao publicada e permanecem intactos porque seus
hashes constam no manifesto canonico. As subpastas novas sao a interface
recomendada para leitura e desenvolvimento futuro.
