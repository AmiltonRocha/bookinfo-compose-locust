# Prova – Microsserviços com Docker Compose e Locust

Aplicação baseada no exemplo **Bookinfo** (Istio), cujas tecnologias batem
exatamente com o diagrama:

| Serviço      | Linguagem | Imagem                                  |
|--------------|-----------|-----------------------------------------|
| Product page | Python    | `istio/examples-bookinfo-productpage-v1`|
| Reviews v1/2/3 | Java    | `istio/examples-bookinfo-reviews-v1/v2/v3` |
| Details      | Ruby      | `istio/examples-bookinfo-details-v1`    |
| Ratings      | Node.js   | `istio/examples-bookinfo-ratings-v1`    |

## a) Isolamento por redes

O Compose, por padrão, coloca todos os serviços na **mesma** rede (todos se
enxergam). Para impor as restrições do enunciado usamos redes separadas:

- `front_reviews`: liga **productpage ↔ reviews** (v1, v2, v3).
- `front_details`: liga **productpage ↔ details**.
- `back_ratings`: liga **reviews v2/v3 ↔ ratings** (o v1 não consulta o Ratings,
  conforme o diagrama).

Assim:

- `productpage` alcança `reviews` e `details` (está nas duas redes de frente).
- `reviews v2/v3` alcançam `ratings` (rede `back_ratings`) e são alcançadas por
  `productpage`, mas **não** alcançam `details` (não compartilham rede).
- `reviews-v1` fica apenas em `front_reviews` (não fala com o Ratings).
- `details` e `ratings` ficam isolados nas suas redes de retaguarda.

O `productpage` chama `http://reviews:9080`; por isso os três contêineres de
reviews recebem o **alias `reviews`** na rede `front_reviews` — o DNS interno do
Docker devolve os três IPs e faz balanceamento round-robin, simulando o serviço
único de reviews do diagrama.

Os nomes das variáveis seguem o código do Bookinfo (`REVIEWS_HOSTNAME`,
`DETAILS_HOSTNAME`, `RATINGS_HOSTNAME`). Como no Bookinfo o v2/v3 só buscam as
avaliações quando `ENABLE_RATINGS=true`, essa variável é definida apenas neles;
o v1 não exibe estrelas.

**Limitação:** o Compose não oferece ACL por sentido do tráfego. O isolamento é
por pertencimento a rede: quem não compartilha rede não se enxerga. Como
`reviews` e `productpage` compartilham `front_reviews`, em tese o `reviews`
poderia iniciar conexões ao `productpage` (a rede é bidirecional). Restringir
*sentido* exigiria política de firewall/NetworkPolicy (ex.: iptables ou
Kubernetes).

## b) Locust isolado no Product page

O Locust **não** pode entrar em `front_reviews` (lá ele alcançaria as reviews).
Por isso criamos a rede dedicada `loadtest`, que contém **apenas** `locust` e
`productpage`. Como `productpage` é o único outro membro dessa rede, o Locust só
consegue atingir o Product page. O alvo é configurado com
`--host http://productpage:9080`, e o `locustfile.py` acessa
`/productpage?u=normal`.

### Métricas do Locust para detectar saturação

O Locust reporta, por endpoint e no agregado: nº de usuários virtuais, RPS
(requisições por segundo), tempo de resposta (média, p50, p95, p99), nº de
falhas e taxa de erro. Para achar o ponto de saturação, observa-se o
comportamento dessas curvas **à medida que se aumenta a carga** (usuários
virtuais):

1. **Tempo de resposta (p95/p99)** – permanece estável enquanto há folga; a
   partir de certo nível cresce de forma acentuada (fila/espera por recursos).
   Esse "joelho" da curva indica o início da saturação.
2. **Throughput (RPS)** – cresce até um máximo e depois **estagna ou cai**,
   mesmo aumentando usuários. É o sintoma clássico de gargalo (Lei de Little:
   ao aumentar a latência, o RPS máximo é limitado).
3. **Taxa de erro / falhas** – timeouts, conexões recusadas e respostas 5xx
   começam a surgir quando o sistema não consegue mais absorver a carga.
4. **Correlação com recursos do host** – o Locust mede apenas o lado do cliente
   (latência, RPS, falhas). Para localizar o gargalo, correlacione a carga com
   `docker stats` (CPU, memória e rede de cada contêiner): CPU/memória saturadas
   no `productpage` ou nas réplicas de `reviews`/`ratings` explicam a queda de
   vazão.

O **ponto de saturação** é a carga (nº de usuários/RPS) imediatamente antes de
a curva de latência disparar e a de throughput deixar de crescer — a partir
dali, adicionar carga só aumenta a latência e os erros, sem ganho de vazão.
