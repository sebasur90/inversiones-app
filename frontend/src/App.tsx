import { ConfigProvider, theme } from 'antd'
import esES from 'antd/locale/es_ES'
import Inversiones from './pages/Inversiones'

export default function App() {
  return (
    <ConfigProvider
      locale={esES}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#58a6ff',
          colorBgBase: '#0d1117',
          colorBgContainer: '#161b22',
          colorBgElevated: '#21262d',
          colorBorder: '#30363d',
          colorText: '#c9d1d9',
          colorTextSecondary: '#8b949e',
          borderRadius: 8,
        },
      }}
    >
      <div style={{ minHeight: '100vh', background: '#0d1117', padding: 24 }}>
        <Inversiones />
      </div>
    </ConfigProvider>
  )
}
