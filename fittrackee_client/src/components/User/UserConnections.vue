<template>
  <div id="user-connections">
    <h1>{{ $t('integrations.TITLE') }}</h1>

    <div v-if="loading" class="loading">{{ $t('common.LOADING') }}</div>
    <template v-else>
      <div v-if="error" class="connection-error">{{ error }}</div>
      <div v-if="success" class="connection-success">{{ success }}</div>

      <section class="connection-card">
        <div class="connection-heading">
          <div>
            <h2>MyWhoosh</h2>
            <p>{{ $t('integrations.MYWHOOSH.DESCRIPTION') }}</p>
          </div>
          <span
            class="connection-state"
            :class="connection.connected ? 'connected' : 'disconnected'"
          >
            {{
              $t(
                `integrations.MYWHOOSH.${
                  connection.connected ? 'CONNECTED' : 'DISCONNECTED'
                }`
              )
            }}
          </span>
        </div>

        <form v-if="!connection.connected" @submit.prevent="connect">
          <label for="mywhoosh-email">{{ $t('user.EMAIL') }}</label>
          <input
            id="mywhoosh-email"
            v-model.trim="credentials.email"
            type="email"
            autocomplete="username"
            required
          />
          <label for="mywhoosh-password">{{ $t('user.PASSWORD') }}</label>
          <input
            id="mywhoosh-password"
            v-model="credentials.password"
            type="password"
            autocomplete="current-password"
            required
          />
          <p class="privacy-note">
            <i class="fa fa-lock" aria-hidden="true" />
            {{ $t('integrations.MYWHOOSH.PASSWORD_NOTE') }}
          </p>
          <button type="submit" :disabled="busy">
            {{ $t('integrations.MYWHOOSH.CONNECT') }}
          </button>
        </form>

        <div v-else>
          <dl>
            <dt>{{ $t('user.EMAIL') }}</dt>
            <dd>{{ connection.email }}</dd>
            <dt>{{ $t('integrations.MYWHOOSH.LAST_SYNC') }}</dt>
            <dd>{{ formatDate(connection.last_sync_at) }}</dd>
            <dt>{{ $t('integrations.MYWHOOSH.STATUS') }}</dt>
            <dd>{{ statusLabel }}</dd>
          </dl>

          <div v-if="connection.last_error" class="connection-error">
            {{ connection.last_error }}
          </div>

          <div class="settings">
            <label class="checkbox-label">
              <input v-model="connection.auto_sync" type="checkbox" />
              {{ $t('integrations.MYWHOOSH.AUTO_SYNC') }}
            </label>
            <label for="sync-days">
              {{ $t('integrations.MYWHOOSH.SYNC_DAYS') }}
            </label>
            <input
              id="sync-days"
              v-model.number="connection.sync_days"
              type="number"
              min="1"
              max="365"
            />
          </div>

          <div class="connection-actions">
            <button :disabled="busy" @click="syncNow">
              {{ $t('integrations.MYWHOOSH.SYNC_NOW') }}
            </button>
            <button :disabled="busy" @click="saveSettings">
              {{ $t('integrations.MYWHOOSH.SAVE_SETTINGS') }}
            </button>
            <button class="danger" :disabled="busy" @click="disconnect">
              {{ $t('integrations.MYWHOOSH.DISCONNECT') }}
            </button>
          </div>
        </div>
      </section>

      <section v-if="connection.imports.length" class="imports">
        <h2>{{ $t('integrations.MYWHOOSH.RECENT_IMPORTS') }}</h2>
        <ul>
          <li v-for="item in connection.imports" :key="item.activity_id">
            <router-link
              v-if="item.workout_id"
              :to="`/workouts/${item.workout_id}`"
            >
              {{ item.activity_title }}
            </router-link>
            <span v-else>{{ item.activity_title }}</span>
            <small>
              {{ formatDate(item.activity_date) }} ·
              {{ $t(`integrations.MYWHOOSH.IMPORT_STATUS.${item.status}`) }}
            </small>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { computed, onBeforeMount, reactive, ref } from 'vue'
  import { useI18n } from 'vue-i18n'

  import authApi from '@/api/authApi'

  interface IMyWhooshImport {
    activity_id: string
    activity_title: string
    activity_date: string | null
    status: string
    error: string | null
    workout_id: string | null
  }

  interface IMyWhooshConnection {
    connected: boolean
    email: string | null
    auto_sync: boolean
    sync_days: number
    last_sync_at: string | null
    last_sync_status: string
    last_error: string | null
    sync_in_progress: boolean
    imports: IMyWhooshImport[]
  }

  const emptyConnection = (): IMyWhooshConnection => ({
    connected: false,
    email: null,
    auto_sync: false,
    sync_days: 30,
    last_sync_at: null,
    last_sync_status: 'never',
    last_error: null,
    sync_in_progress: false,
    imports: [],
  })

  const loading = ref(true)
  const busy = ref(false)
  const error = ref('')
  const success = ref('')
  const connection = reactive<IMyWhooshConnection>(emptyConnection())
  const credentials = reactive({ email: '', password: '' })
  const { t } = useI18n()

  const statusLabel = computed(() =>
    connection.sync_in_progress
      ? t('integrations.MYWHOOSH.STATUS_VALUES.in_progress')
      : t(`integrations.MYWHOOSH.STATUS_VALUES.${connection.last_sync_status}`)
  )

  function updateConnection(data: IMyWhooshConnection) {
    Object.assign(connection, emptyConnection(), data)
  }

  function getErrorMessage(exception: unknown): string {
    const apiError = exception as {
      response?: { data?: { message?: string } }
    }
    return (
      apiError.response?.data?.message ||
      t('integrations.MYWHOOSH.GENERIC_ERROR')
    )
  }

  function formatDate(value: string | null): string {
    return value ? new Date(value).toLocaleString() : '—'
  }

  async function loadConnection() {
    loading.value = true
    error.value = ''
    try {
      const response = await authApi.get('integrations/mywhoosh')
      updateConnection(response.data.data)
    } catch (exception) {
      error.value = getErrorMessage(exception)
    } finally {
      loading.value = false
    }
  }

  async function connect() {
    busy.value = true
    error.value = ''
    success.value = ''
    try {
      const response = await authApi.post('integrations/mywhoosh/connect', {
        email: credentials.email,
        password: credentials.password,
      })
      updateConnection(response.data.data)
      credentials.password = ''
      success.value = t('integrations.MYWHOOSH.CONNECT_SUCCESS')
    } catch (exception) {
      error.value = getErrorMessage(exception)
    } finally {
      busy.value = false
    }
  }

  async function saveSettings() {
    busy.value = true
    error.value = ''
    success.value = ''
    try {
      const response = await authApi.patch('integrations/mywhoosh/settings', {
        auto_sync: connection.auto_sync,
        sync_days: connection.sync_days,
      })
      updateConnection(response.data.data)
      success.value = t('integrations.MYWHOOSH.SETTINGS_SUCCESS')
    } catch (exception) {
      error.value = getErrorMessage(exception)
    } finally {
      busy.value = false
    }
  }

  async function syncNow() {
    busy.value = true
    error.value = ''
    success.value = ''
    try {
      const response = await authApi.post('integrations/mywhoosh/sync')
      updateConnection(response.data.data.connection)
      const summary = response.data.data.summary
      success.value = t('integrations.MYWHOOSH.SYNC_SUCCESS', summary)
    } catch (exception) {
      error.value = getErrorMessage(exception)
      await loadConnection()
    } finally {
      busy.value = false
    }
  }

  async function disconnect() {
    if (!window.confirm(t('integrations.MYWHOOSH.DISCONNECT_CONFIRM'))) return
    busy.value = true
    error.value = ''
    success.value = ''
    try {
      const response = await authApi.delete('integrations/mywhoosh/disconnect')
      updateConnection(response.data.data)
      success.value = t('integrations.MYWHOOSH.DISCONNECT_SUCCESS')
    } catch (exception) {
      error.value = getErrorMessage(exception)
    } finally {
      busy.value = false
    }
  }

  onBeforeMount(loadConnection)
</script>

<style scoped lang="scss">
  @use '~@/scss/vars.scss' as *;

  #user-connections {
    padding-bottom: $default-padding;
  }

  h1,
  h2 {
    font-size: 1.05em;
  }

  .connection-card {
    border: 1px solid var(--card-border-color);
    border-radius: $border-radius;
    padding: $default-padding * 1.5;
  }

  .connection-heading {
    display: flex;
    justify-content: space-between;
    gap: $default-padding;
  }

  .connection-state {
    align-self: flex-start;
    border-radius: 1em;
    padding: 3px 10px;
    white-space: nowrap;

    &.connected {
      background: #d7f4e4;
      color: #17663b;
    }

    &.disconnected {
      background: var(--alert-background-color);
      color: var(--alert-color);
    }
  }

  form,
  .settings {
    display: grid;
    gap: $default-padding * 0.5;
    margin-top: $default-margin;
  }

  input[type='email'],
  input[type='password'],
  input[type='number'] {
    box-sizing: border-box;
    padding: $default-padding * 0.5;
    width: 100%;
  }

  .privacy-note,
  small {
    color: var(--app-color);
    font-size: 0.85em;
    opacity: 0.8;
  }

  .connection-actions {
    display: flex;
    flex-wrap: wrap;
    gap: $default-padding;
    margin-top: $default-margin;
  }

  .danger {
    margin-left: auto;
  }

  .connection-error,
  .connection-success {
    border-radius: $border-radius;
    margin: $default-margin 0;
    padding: $default-padding;
  }

  .connection-error {
    background: var(--alert-background-color);
    color: var(--alert-color);
  }

  .connection-success {
    background: #d7f4e4;
    color: #17663b;
  }

  .imports {
    margin-top: $default-margin * 2;

    ul {
      padding-left: $default-padding * 2;
    }

    li {
      margin-bottom: $default-margin;
    }

    small {
      display: block;
    }
  }

  @media screen and (max-width: $small-limit) {
    .connection-heading {
      flex-direction: column;
    }

    .danger {
      margin-left: 0;
    }
  }
</style>
