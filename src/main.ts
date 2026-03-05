import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

// 创建Vue应用实例
const app = createApp(App)

// 使用路由
app.use(router)
app.use(createPinia())
app.use(ElementPlus)

// 挂载应用
app.mount('#app')
