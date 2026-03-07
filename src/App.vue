<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-header-inner">
        <div class="brand">
          <div class="brand-mark">
            AVS
          </div>
          <div>
            <div class="brand-title">AVS System</div>
            <div class="brand-subtitle">视频发声物体分割</div>
          </div>
        </div>

        <nav class="app-nav">
          <RouterLink to="/" class="nav-link">工作台</RouterLink>
          <RouterLink to="/tasks" class="nav-link">任务中心</RouterLink>
          <RouterLink to="/admin" class="nav-link">管理员</RouterLink>
        </nav>
      </div>
    </header>

    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>
