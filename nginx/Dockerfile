# Nginx як балансувальник навантаження для реплік Vet CRM.
# Версія 1.28: параметр `resolve` в upstream (динамічне оновлення списку реплік) доступний у відкритій версії.
FROM nginx:1.28-alpine

# Вибір алгоритму балансування — виконується при старті, до підстановки змінних у шаблон
COPY 05-lb-algorithm.envsh /docker-entrypoint.d/05-lb-algorithm.envsh
RUN chmod +x /docker-entrypoint.d/05-lb-algorithm.envsh

# Шаблон конфігурації: при старті перетворюється на /etc/nginx/conf.d/default.conf
COPY templates/ /etc/nginx/templates/
