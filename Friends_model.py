import torch
import torch.nn as nn
from torch.nn import functional as F


# Hyper Parameters

batch_size = 64
block_size = 256
max_iters = 5000
eval_interval = 500
learning_rate = 3e-4
device = 'cuda' if torch.cuda.is_available() else 'cpu'
eval_iters = 200
n_embd = 384
n_head = 6
n_layer = 6
dropout = 0.2

torch.manual_seed(42)
print(device)

with open('Friends_script.txt','r',encoding='utf-8') as f:
    text = f.read()



chars = sorted(list(set(text)))
vocab_size = len(chars)


stoi = {ch:i for i,ch in enumerate(chars)}
itos = {i:ch for i,ch in enumerate(chars)}
encode = lambda s: [stoi[c] for c in s]
decode = lambda l:''.join([itos[i] for i in l])


data = torch.tensor(encode(text),dtype=torch.long)


n = int(0.9*len(data))
train_data=data[:n]
val_data = data[n:]



def get_batch(split):
    data = train_data if split == 'train' else val_data
    ix = torch.randint(len(data)-block_size,(batch_size,))
    x = torch.stack([data[i:i+block_size]for i in ix])
    y= torch.stack([data[i+1:i+block_size+1]for i in ix])
    return x,y


@torch.no_grad()
def estimate_loss():
    out = {}
    model.eval()
    for split in ['train','val']:
        losses = torch.zeros(eval_iters)
        for k in range(eval_iters):
            X,Y = get_batch(split)
            X,Y = X.to(device), Y.to(device)
            logits,loss = model(X,Y)
            losses[k] = loss.item()
        out[split] = losses.mean()
    model.train()
    return out





class Head(nn.Module):
    """ Implements one head of self attention """
    def __init__(self,head_size):
        super().__init__()
        self.key = nn.Linear(n_embd,head_size,bias=False)
        self.value = nn.Linear(n_embd,head_size,bias=False)
        self.query = nn.Linear(n_embd,head_size,bias=False)
        self.register_buffer('tril',torch.tril(torch.ones(block_size,block_size)))
        self.dropout = nn.Dropout(dropout)
    
    def forward(self,x):
        B,T,C  = x.shape
        k = self.key(x)
        q = self.query(x)


        wei = q @ k.transpose(-1,-2) * C**(-0.5)
        wei = wei.masked_fill(self.tril[:T,:T]==0,float('-inf'))
        wei = F.softmax(wei,dim=  -1)
        wei = self.dropout(wei)


        v = self.value(x)
        out = wei @ v
        return out
    



class MultiHeadAttention(nn.Module):
    """ Multiple heads of self attention in parallel"""
    def __init__(self,num_heads,head_size):
        super().__init__()
        self.heads = nn.ModuleList([Head(head_size) for _ in range(num_heads)])
        self.proj = nn.Linear(num_heads*head_size,n_embd)
        self.dropout = nn.Dropout(dropout)
    

    def forward(self,x):
        out=  torch.cat([h(x) for h in self.heads],dim= -1)
        out = self.proj(out)
        out = self.dropout(out)
        return out
    



class FeedForward(nn.Module):
    """ Feed forward layer . Note -> Feed forward network works at a token level (independent)"""

    def __init__(self,n_embd):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.ReLU(),
            nn.Linear(4 * n_embd,n_embd),
            nn.Dropout(dropout),
        )

    def forward(self,x):
        return self.net(x)




class Block(nn.Module):
    """ Transformer block (decoder sec) : Communication followed by computation"""


    def __init__(self,n_embd,n_head):
        super().__init__()
        head_size = n_embd // n_head
        self.sa = MultiHeadAttention(n_head,head_size=head_size)
        self.ffwd = FeedForward(n_embd)
        self.ln1 = nn.LayerNorm(n_embd)
        self.ln2 = nn.LayerNorm(n_embd)
    
    def forward(self,x):
        # x = self.sa(x)
        # x = self.ffwd(x)
        x = self.ln1(x)
        x = x+ self.sa(x)
        x = self.ln2(x)
        x = x + self.ffwd(x)


        return x





class BigramLanguageModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.token_embedding_table = nn.Embedding(vocab_size,n_embd)
        self.position_embedding_table = nn.Embedding(block_size,n_embd)
        # self.sa_heads = MultiHeadAttention(4,n_embd//4)  # Head -> 32 dim, now split into 4 sets of 8 dim
        # self.ffwd = FeedForward(n_embd)
        self.blocks = nn.Sequential(*[Block(n_embd,n_head=n_head) for _ in range(n_layer)])
        self.lm_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd,vocab_size)


    def forward(self,idx,targets=None):


        B,T = idx.shape

        token_emb = self.token_embedding_table(idx) # (B,T,C)
        pos_emb = self.position_embedding_table(torch.arange(T,device=device)) # (T,C)
        x = token_emb+pos_emb  # (B,T,C)
        # x = self.sa_heads(x)
        # x = self.ffwd(x)
        x = self.blocks(x)
        logits =self.lm_head(x)  # (B,T,vocab_size)
        if targets == None:
            loss = None
        else:
            B, T,C = logits.shape
            logits = logits.view(B*T,C)
            targets = targets.view(B*T)
            loss = F.cross_entropy(logits,targets)
        return logits,loss



    def generate(self,idx,max_new_tokens):
        for _ in range(max_new_tokens):
            # Crop idx to only the last block_size tokens
            idx_cond = idx[:,-block_size:]
            logits,loss = self(idx_cond)
            # Focus only on the last time step
            logits = logits[:,-1,:] # Becomes (B,C)
            probs = F.softmax(logits,dim = -1) # (B,C)
            idx_next = torch.multinomial(probs,num_samples = 1) # (B,1)
            idx = torch.cat((idx,idx_next),dim = 1) #(B,T+1)
        return idx
    

model = BigramLanguageModel()
m = model.to(device)

optimizer = torch.optim.AdamW(model.parameters(),lr=learning_rate)
for iter in range(max_iters):
    if iter % eval_interval == 0:
        losses = estimate_loss()
        print(f"Epoch : {iter} | train loss : {losses['train']:.4f} | val losses: {losses['val']:.4f}")
    

    xb,yb = get_batch('train')
    xb, yb = xb.to(device), yb.to(device)
    logits,loss = model(xb,yb)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()


context = torch.zeros((1,1),dtype = torch.long,device = device)
print(decode(m.generate(context,max_new_tokens=500)[0].tolist()))



  
