import { Routes, Route } from 'react-router-dom'
import { Layout } from './components'
import {
  Dashboard,
  Games,
  GameDetail,
  Trends,
  Compare,
  Focus,
  Players,
  PlayerDetail,
} from './pages'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="games" element={<Games />} />
        <Route path="games/:replayId" element={<GameDetail />} />
        <Route path="trends" element={<Trends />} />
        <Route path="compare" element={<Compare />} />
        <Route path="focus" element={<Focus />} />
        <Route path="players" element={<Players />} />
        <Route path="players/:playerId" element={<PlayerDetail />} />
      </Route>
    </Routes>
  )
}

export default App
