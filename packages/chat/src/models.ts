/**
 * Model Configuration for JupyterLab Chat
 * 
 * This file defines all available models and their corresponding providers.
 * When a model is selected, the provider is automatically inferred.
 */

export interface ModelConfig {
  id: string;
  name: string;
  provider: 'openai' | 'claude' | 'gemini';
  description?: string;
}

export const AVAILABLE_MODELS: ModelConfig[] = [
  // OpenAI Models
  {
    id: 'gpt-4o',
    name: 'GPT-4o',
    provider: 'openai',
    description: 'Most capable OpenAI model'
  },
  {
    id: 'gpt-4o-mini',
    name: 'GPT-4o Mini',
    provider: 'openai',
    description: 'Faster, cost-effective OpenAI model'
  },
  {
    id: 'o1-preview',
    name: 'o1-preview',
    provider: 'openai',
    description: 'Advanced reasoning model'
  },
  {
    id: 'o1-mini',
    name: 'o1-mini',
    provider: 'openai',
    description: 'Compact reasoning model'
  },
  {
    id: 'gpt-4-turbo',
    name: 'GPT-4 Turbo',
    provider: 'openai',
    description: 'High performance GPT-4'
  },
  {
    id: 'gpt-3.5-turbo',
    name: 'GPT-3.5 Turbo',
    provider: 'openai',
    description: 'Fast and efficient'
  },
  
  // Claude Models
  {
    id: 'claude-3-5-sonnet-20241022',
    name: 'Claude 3.5 Sonnet',
    provider: 'claude',
    description: 'Most capable Claude model'
  },
  {
    id: 'claude-3-5-haiku-20241022',
    name: 'Claude 3.5 Haiku',
    provider: 'claude',
    description: 'Fast Claude model'
  },
  {
    id: 'claude-3-opus-20240229',
    name: 'Claude 3 Opus',
    provider: 'claude',
    description: 'Powerful reasoning model'
  },
  
  // Gemini Models
  {
    id: 'gemini-2.0-flash-exp',
    name: 'Gemini 2.0 Flash',
    provider: 'gemini',
    description: 'Latest Gemini model with implicit caching'
  },
  {
    id: 'gemini-pro',
    name: 'Gemini Pro',
    provider: 'gemini',
    description: 'Google\'s advanced model'
  }
];

/**
 * Get provider for a given model ID
 */
export function getProviderForModel(modelId: string): string {
  const model = AVAILABLE_MODELS.find(m => m.id === modelId);
  return model?.provider || 'openai';
}

/**
 * Get model configuration by ID
 */
export function getModelConfig(modelId: string): ModelConfig | undefined {
  return AVAILABLE_MODELS.find(m => m.id === modelId);
}

/**
 * Get all models for a specific provider
 */
export function getModelsForProvider(provider: string): ModelConfig[] {
  return AVAILABLE_MODELS.filter(m => m.provider === provider);
} 