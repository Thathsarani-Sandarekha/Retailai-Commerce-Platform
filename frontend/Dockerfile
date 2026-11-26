# Build the Next.js customer and operations applications as one service.
FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build \
    && chown -R node:node /app
ENV NODE_ENV=production
USER node
EXPOSE 3000
CMD ["npm", "run", "start:docker"]
