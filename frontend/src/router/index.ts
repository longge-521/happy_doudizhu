// frontend/src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', name: 'Login', component: () => import('@/views/LoginView.vue') },
    { path: '/lobby', name: 'Lobby', component: () => import('@/views/LobbyView.vue') },
    { path: '/game/:roomId?', name: 'Game', component: () => import('@/views/GameRoomView.vue') },
  ],
})

export default router
